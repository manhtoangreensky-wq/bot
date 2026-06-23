import asyncio
import inspect
from types import SimpleNamespace

import bot


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def _session(scene_count=3):
    return {
        "prompt": "Quảng cáo cà phê Việt Nam",
        "original_prompt": "coffee ad",
        "selected_scene_count": scene_count,
        "scene_count": scene_count,
        "estimated_scene_seconds": 6,
        "aspect_ratio": "9:16",
        "language": "vi",
        "platform": "TikTok/Reels/Shorts",
        "selected_video_tier": "basic",
        "video_tier": "basic",
        "current_video_price_preview": {"total_xu": 300, "scene_count": scene_count},
    }


def test_default_tts_ready_independent_from_clone_not_tested(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "last_tts_smoke": "PASS",
            "reason": "ready",
        },
    )
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *args: "PASS" if "minimax_tts" in args else "NOT_TESTED")

    readiness = bot._product_engine_readiness("voice_tts", "tts")

    assert readiness["configured"] is True
    assert readiness["public_ready"] is True
    assert bot.engine_technical_missing(readiness) == []


def test_voice_tts_execute_engine_does_not_call_clone(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "last_tts_smoke": "PASS"},
    )
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *args: "PASS")

    async def fake_tts(*_args, **_kwargs):
        return True, b"real-audio", "tts"

    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", fake_tts)
    monkeypatch.setattr(
        bot,
        "create_minimax_voice_profile_preview",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("voice clone route must not run for default TTS")),
    )

    result = asyncio.run(
        bot.execute_engine(
            "voice_tts",
            {"text": "Xin chao"},
            {
                "user_id": 1,
                "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
                "confirm_paid": True,
                "admin_interactive_confirm": True,
                "is_paid_job": True,
            },
        )
    )

    assert result["ok"] is True
    assert result["has_output_bytes"] is True
    assert result["output_bytes"] == b"real-audio"


def test_clone_forbidden_maps_to_clone_permission_forbidden():
    route_error = bot.voice_clone_route_error(
        "key4u_minimax",
        "voice_clone",
        "clone",
        "FAIL_PROVIDER_ERROR",
        "voice clone user forbidden",
    )

    assert bot.voice_clone_not_ready_status([route_error]) == "CLONE_PERMISSION_FORBIDDEN"
    assert bot.voice_clone_preview_fail_category("voice clone user forbidden", {"ready": True}, [route_error]) == "CLONE_PERMISSION_FORBIDDEN"


def test_failed_voice_profile_cannot_be_default_or_tts(monkeypatch):
    failed_profile = {
        "id": 7,
        "user_id": "1",
        "status": "failed_clone_permission_forbidden",
        "provider_voice_id": "provider-voice-id",
    }
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda *_args: failed_profile)

    assert bot.voice_profile_can_generate_tts(failed_profile) is False
    assert bot.set_default_voice_profile(1, 7) is False


def test_voice_public_clone_guard_clean_exact():
    text = bot.voice_clone_provider_not_ready_public_text("vi")

    assert text == bot.VOICE_CLONE_PROVIDER_NOT_READY_PUBLIC_VI
    for term in ("provider", "api", "key4u", "shopaikey", "minimax", "forbidden", "debug"):
        assert term not in text.lower()


def test_music_song_incomplete_full_result_allows_admin_real_lifecycle(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "fetch_ready": True,
            "download_ready": False,
            "full_result_ok": False,
            "reason": "fetch_processing",
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

    assert decision["status"] == "allowed_admin"
    assert "music_download_not_ready" not in bot.engine_technical_missing(decision["readiness"])
    assert "music_full_result_not_ready" not in bot.engine_technical_missing(decision["readiness"])
    assert "music_download_not_ready" in decision["readiness"]["public_blockers"]
    assert "music_full_result_not_ready" in decision["readiness"]["public_blockers"]
    assert "Đã trừ: 0 Xu" not in decision["message"]


def test_music_status_success_requires_downloaded_audio_bytes():
    source = inspect.getsource(bot.handle_music_quick_callback)
    status_block = source[source.index('if action == "music_ai_status":'):]

    assert "_download_audio_url_bytes(output_url" in status_block
    assert 'download_status="PASS" if audio_bytes else "FAIL_DOWNLOAD"' in status_block
    assert "audio=output_url" not in status_block


def test_music_poll_missing_status_route_fails_explicitly(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_STATUS_ENDPOINT", "")

    result = asyncio.run(
        bot.poll_music_generation_job(
            {"music_provider": "shopaikey_music", "music_task_id": "real-task-id"},
            updated_by=1,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "MISSING_STATUS_ROUTE"


def test_dub_mode_disabled_not_asr_or_tts_missing(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)

    readiness = bot._product_engine_readiness("video_dub", bot.VIDEO_SUBTITLE_MODE_DUB)
    missing = bot.engine_technical_missing(readiness)

    assert missing == ["mode_disabled"]
    assert "asr_adapter_missing" not in missing
    assert "video_dub_tts_adapter_missing" not in missing


def test_asr_not_missing_when_deepgram_registered(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "AgentDeepgram", object)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)

    cap = bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_DUB, {}, public=False)

    assert "asr" not in cap.get("missing", [])


def test_dub_tts_not_missing_when_minimax_tts_smoke_pass(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "video_asr_provider_available_for", lambda public=True: True)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *args: "PASS")
    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=True: True)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_configured", lambda: False)
    monkeypatch.setattr(bot, "direct_minimax_tts_configured", lambda: False)
    monkeypatch.setattr(bot, "TTS_PROVIDER", "minimax")

    cap = bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_DUB, {}, public=False)

    assert "tts" not in cap.get("missing", [])


def test_dub_pipeline_returns_partial_srt_when_mux_disabled():
    source = inspect.getsource(bot.execute_video_dubbing_pipeline)

    assert "VIDEO_SUBTITLE_MODE_DUB" in source
    assert "if wants_subtitle_video and not VIDEO_SUBTITLE_BURN_IN_ENABLED" not in source
    assert "not (srt_bytes or audio_bytes or video_output)" in source
    assert 'output_type not in {"burn", "video", "video_subtitle"}' in source


def test_video_multiscene_status_command_exists():
    source = open(bot.__file__, encoding="utf-8").read()

    assert 'CommandHandler("video_multiscene_engine_status", cmd_video_multiscene_status)' in source


def test_multiscene_status_exact_missing_components(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_CREATE_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_QUERY_ENDPOINT", "")
    monkeypatch.setattr(bot, "KEY4U_VIDEO_MODEL", "")
    monkeypatch.setattr(bot, "video_multiscene_queue_available", lambda: False)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False})
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: False)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: False)
    monkeypatch.setattr(bot, "video_multiscene_scene_tested", lambda _count: False)

    missing = bot.video_multiscene_missing_components(20, include_smoke=True)

    for component in (
        "video_provider_missing",
        "video_submit_route_missing",
        "video_status_route_missing",
        "queue_missing",
        "local_worker_missing",
        "ffmpeg_missing",
        "stitcher_missing",
        "multiscene_smoke_not_tested",
    ):
        assert component in missing


def test_multiscene_admin_test_can_verify_unverified_stitcher(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://example.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "model")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", False)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: True)
    monkeypatch.setattr(bot, "video_multiscene_queue_available", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: False)
    ids = iter([9001, 9002, 9003, 9004])
    monkeypatch.setattr(bot, "create_shopaikey_job", lambda *_args, **_kwargs: next(ids))
    monkeypatch.setattr(bot, "update_shopaikey_job", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "save_multiscene_job_record", lambda job: job)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "set_system_setting", lambda *_args, **_kwargs: True)

    async def submit_scene(child):
        return {"status": "PASS_SUBMITTED", "task_id": f"scene-{child['scene_index']}", "provider_route": "shopaikey"}

    async def poll_scene(child):
        output = tmp_path / f"scene_{child['scene_index']}.mp4"
        output.write_bytes(b"scene-video")
        return {"status": "COMPLETED", "output_url": str(output)}

    def stitch_scene(scene_files, output_path, _aspect, _settings):
        assert len(scene_files) == 3
        with open(output_path, "wb") as handle:
            handle.write(b"stitched-video")
        return {"status": "COMPLETED", "output_path": output_path}

    async def fake_sender(*_args, **_kwargs):
        return {"sent": True}

    result = asyncio.run(
        bot.run_multiscene_video_job(
            {"session": _session(3), "admin_test": True, "confirm_paid": True},
            submitter=submit_scene,
            poller=poll_scene,
            stitcher=stitch_scene,
            sender=fake_sender,
        )
    )

    assert result["status"] in {"SENT", "COMPLETED"}
    assert result["final_output"]


def test_video_multiscene_public_guard_copy():
    assert bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT == (
        "Tạo video nhiều cảnh đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
    )


def test_runtime_warning_exact_copy():
    source = open(bot.__file__, encoding="utf-8").read()
    exact = (
        "Railway ENV TELEGRAM_UPDATE_MODE đang bị dính nhiều dòng. "
        "Hãy đặt TELEGRAM_UPDATE_MODE=webhook và BOT_USERNAME=toanaasbot ở hai biến riêng."
    )

    assert exact in source
