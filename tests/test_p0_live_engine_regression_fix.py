import asyncio
from types import SimpleNamespace

import bot


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def test_song_legacy_half_normalizes_to_full_without_short_mode(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", False)
    half = {"song_product": "half", "guided_duration_seconds": 60, "selected_prompt": "bài hát có lời"}
    full = {"song_product": "full", "guided_duration_seconds": 120, "selected_prompt": "bài hát có lời"}

    half_text = bot.music_ai_preview_text(half, "vi")
    full_text = bot.music_ai_preview_text(full, "vi")

    assert "Nghe thử bài hát có lời AI" in half_text
    assert "Nửa bài." not in half_text
    assert f"Bản đầy đủ bài hát có lời AI: <b>{bot.music_result_price_xu(half)} Xu</b>" in half_text
    assert "Nghe thử bài hát có lời AI" in full_text
    assert "Bản đầy đủ được lưu trong kho" in full_text
    assert f"Bản đầy đủ bài hát có lời AI: <b>{bot.music_result_price_xu(full)} Xu</b>" in full_text
    assert "Thời lượng bản đầy đủ" not in half_text
    assert "Thời lượng bản đầy đủ" not in full_text
    assert "60 giây" not in half_text


def test_song_half_full_new_state_uses_song_length_mode():
    source = open(bot.__file__, encoding="utf-8").read()
    start = source.index('if action in {"song_start_half", "song_start_full"}:')
    end = source.index('if action == "song_duration_custom":', start)
    block = source[start:end]

    assert '"song_length_mode": product' in block
    assert '"guided_duration_seconds"' not in block
    assert '"guided_duration":' not in block


def test_admin_subtitle_mode_disabled_is_exact_blocker_not_adapter_missing(monkeypatch):
    _admin_only(monkeypatch)

    def feature_flag_capability(_mode, _state=None, public=True):
        return {"ok": False, "reason": "mode_disabled", "missing": ["mode_disabled"]}

    monkeypatch.setattr(bot, "video_dubbing_capability", feature_flag_capability)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "video_asr_provider_available", lambda: True)
    monkeypatch.setattr(bot, "video_translation_provider_available", lambda: True)
    monkeypatch.setattr(bot, "video_tts_provider_available", lambda: True)

    decision = bot.can_user_access_product_engine(
        1,
        "subtitle_translate",
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        is_provider_call=True,
    )

    assert decision["status"] == "blocked_admin_missing_provider_config"
    assert bot.engine_technical_missing(decision["readiness"]) == ["mode_disabled"]
    admin_text = bot.admin_product_engine_missing_text("subtitle_translate", decision["readiness"])
    assert "mode_disabled" in admin_text
    assert "asr_adapter_missing" not in admin_text
    assert "video_dub_tts_adapter_missing" not in admin_text
    assert "feature_flag" not in admin_text


def test_video_multiscene_public_flag_does_not_render_generic_adapter_blocker(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://example.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "model")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_queue_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_scene_tested", lambda _scene_count: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _scene_count: False)

    admin_decision = bot.can_user_access_product_engine(1, "video_multiscene", "3", is_provider_call=True)
    public_decision = bot.can_user_access_product_engine(2, "video_multiscene", "3", is_provider_call=True)
    admin_text = bot.admin_product_engine_missing_text("video_multiscene", admin_decision["readiness"])

    assert admin_decision["status"] == "allowed_admin"
    assert public_decision["status"] == "blocked_public_maintenance"
    assert bot.engine_technical_missing(admin_decision["readiness"]) == []
    assert "video_multiscene_adapter" not in admin_text
    assert "adapter chưa sẵn sàng" not in admin_text
    assert "feature_flag" not in admin_text


def test_video_multiscene_missing_components_are_exact(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_CREATE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_MODEL", "")
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: False)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _scene_count: False)

    readiness = bot._product_engine_readiness("video_multiscene", "3")
    missing = bot.engine_technical_missing(readiness)
    admin_text = bot.admin_product_engine_missing_text("video_multiscene", readiness)

    assert "video_provider_missing" in missing
    assert "ffmpeg_missing" in missing
    assert "video_provider_missing" in admin_text
    assert "ffmpeg_missing" in admin_text
    assert "feature_flag" not in admin_text


def test_voice_preview_admin_failure_diagnostic_has_safe_fields():
    text = bot.voice_clone_admin_preview_failure_text(
        {
            "ready": True,
            "routes": ["key4u_minimax"],
            "tts_smoke": "PASS",
            "clone_smoke": "FAIL",
        },
        output_bytes=0,
        route_errors=["key4u_minimax:preview:FAIL:no_audio"],
        error="voice_routes_failed",
    )

    assert "selected_adapter" in text
    assert "configured" in text
    assert "tts_smoke" in text
    assert "clone_smoke" in text
    assert "output_bytes" in text
    assert "fail_category" in text
    assert "PROVIDER_ROUTE_FAILED" in text
    assert "api_key" not in text.lower()
    assert "bearer " not in text.lower()


def test_slash_start_short_circuits_before_pending_handlers(monkeypatch):
    called = {"start": False}

    async def fake_cmd_start(_update, _context):
        called["start"] = True

    async def pending_must_not_run(_update, _context):
        raise AssertionError("pending handler should not run for /start")

    monkeypatch.setattr(bot, "cmd_start", fake_cmd_start)
    monkeypatch.setattr(bot, "handle_manual_approval_pending_text", pending_must_not_run)

    update = SimpleNamespace(
        message=SimpleNamespace(text="/start"),
        effective_user=SimpleNamespace(id=123, first_name="Test", username="test"),
    )
    context = SimpleNamespace(args=[])

    asyncio.run(bot.handle_message(update, context))

    assert called["start"] is True


def test_clear_pending_start_notice_removes_shopaikey_confirmations():
    uid = "p0-live-regression-user"
    token = bot.set_shopaikey_pending_confirmation(uid, {"job_type": "video"})

    assert token in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
    assert bot.clear_pending_start_notice(uid)
    assert token not in bot.SHOPAIKEY_PENDING_CONFIRMATIONS
