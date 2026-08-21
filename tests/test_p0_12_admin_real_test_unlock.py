import inspect

import bot


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_admin_real_test_bypasses_public_ready(monkeypatch):
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
            "reason": "configured_for_admin_lifecycle",
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
    public_decision = bot.can_user_access_product_engine(2, "music_song", "confirm", is_provider_call=True)

    assert decision["status"] == "allowed_admin"
    assert "music_download_not_ready" not in bot.engine_technical_missing(decision["readiness"])
    assert "music_full_result_not_ready" not in bot.engine_technical_missing(decision["readiness"])
    assert public_decision["status"] == "blocked_public_maintenance"


def test_admin_real_test_requires_explicit_confirm(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "fetch_ready": True, "download_ready": False, "full_result_ok": False},
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

    decision = bot.can_user_access_product_engine(1, "music_song", "confirm", is_provider_call=True, is_paid_job=True)

    assert decision["status"] == "blocked_admin_requires_confirm"


def test_admin_real_test_does_not_bypass_missing_component(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "fetch_ready": False, "download_ready": False, "full_result_ok": False},
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

    assert decision["status"] == "blocked_admin_missing_provider_config"
    assert "music_status_route_missing" in bot.engine_technical_missing(decision["readiness"])


def test_admin_real_test_bypasses_mode_disabled(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "AgentDeepgram", object)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)
    monkeypatch.setattr(
        bot,
        "video_dubbing_capability",
        lambda mode, state=None, public=False: {"ok": True, "reason": "ready", "missing": []} if not public else {"ok": False, "reason": "mode_disabled", "missing": ["mode_disabled"]},
    )

    admin_decision = bot.can_user_access_product_engine(
        1,
        "video_dub",
        bot.VIDEO_SUBTITLE_MODE_DUB,
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )
    public_decision = bot.can_user_access_product_engine(2, "video_dub", bot.VIDEO_SUBTITLE_MODE_DUB, is_provider_call=True)

    assert admin_decision["status"] == "allowed_admin"
    assert public_decision["status"] in {"allowed_public", "blocked_public_maintenance"}


def test_admin_real_test_mode_disabled_still_blocks_missing_asr(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)

    decision = bot.can_user_access_product_engine(
        1,
        "video_dub",
        bot.VIDEO_SUBTITLE_MODE_DUB,
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )

    assert decision["status"] == "blocked_admin_missing_provider_config"
    assert "asr_adapter_missing" in bot.engine_technical_missing(decision["readiness"])


def test_admin_multiscene_smoke_offer_when_stitch_unverified(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "video_multiscene_route_state", lambda: {"provider_ready": True, "submit_route_ready": True, "status_route_ready": True})
    monkeypatch.setattr(bot, "video_multiscene_queue_available", lambda: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: False)
    monkeypatch.setattr(bot, "video_multiscene_scene_tested", lambda _count: False)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: False)

    decision = bot.can_user_access_product_engine(
        1,
        "video_multiscene",
        "3",
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )
    status = bot.video_multiscene_status_payload()

    assert decision["status"] == "allowed_admin"
    assert status["admin_multiscene_smoke_ready"] is True
    assert "stitcher_missing" in status["exact_missing_components"]
    assert "stitcher_missing" not in status["admin_missing_components"]


def test_public_multiscene_still_guarded(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: False)

    decision = bot.can_user_access_product_engine(2, "video_multiscene", "3", is_provider_call=True)

    assert decision["status"] == "blocked_public_maintenance"


def test_multiscene_success_requires_scene_and_stitch_bytes():
    source = inspect.getsource(bot._execute_multiscene_video_job)

    assert "scene_output_empty" in source
    assert "stitch_output_empty" in source


def test_clone_forbidden_blocks_clone_but_not_default_tts(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_clone_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "provider_permission_blocked": True,
            "reason": "clone_permission_forbidden",
        },
    )
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "last_tts_smoke": "PASS"},
    )
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *args: "PASS")

    clone_decision = bot.can_user_access_product_engine(
        1,
        "voice_clone",
        "clone",
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )
    tts_decision = bot.can_user_access_product_engine(
        1,
        "voice_tts",
        "tts",
        is_provider_call=True,
        is_paid_job=True,
        confirm_paid=True,
        admin_interactive_confirm=True,
    )

    assert clone_decision["status"] == "blocked_admin_missing_provider_config"
    assert "clone_permission_forbidden" in bot.engine_technical_missing(clone_decision["readiness"])
    assert tts_decision["status"] == "allowed_admin"


def test_clone_forbidden_hides_retry_button_and_suggests_default_tts(monkeypatch):
    _admin_only(monkeypatch)
    profile = {"id": 7, "user_id": "1", "display_name": "Giọng test", "status": "failed_clone_permission_forbidden"}

    labels = _labels(bot.voice_profile_actions_keyboard(7, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile))
    text = bot.voice_profile_not_ready_text(profile, "vi")

    assert "🔁 Tạo/nghe thử lại" in labels
    assert "⬅️ Kho voice" in labels
    assert "Tạo voice riêng đang tạm khóa" in text
    assert "chưa xử lý và chưa trừ Xu" in text


def test_status_reports_admin_test_ready_separate_from_public_ready(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {
            "ready": True,
            "public_enabled": False,
            "missing_env": [],
            "fetch_ready": True,
            "download_ready": False,
            "full_result_ready": False,
            "full_result_ok": False,
            "providers": {"key4u_suno": {"configured": True}, "shopaikey_music": {"configured": False}},
            "preferred_provider": "key4u_suno",
            "cost_gate_ok": True,
        },
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)
    monkeypatch.setattr(bot, "preferred_tool_test_result", lambda *args: {"status": "PASS"} if "key4u_suno" in args else {"status": "NOT_TESTED"})

    text = "\n".join(bot.music_engine_status_lines())

    assert "admin_submit_ready" in text
    assert "partial lifecycle possible" in text
    assert "Public ready" in text
    assert "API_KEY" not in text


def test_admin_product_commands_registered_and_require_confirm():
    source = open(bot.__file__, encoding="utf-8").read()

    assert 'CommandHandler("tool_test_voice_tts_product", cmd_tool_test_voice_tts_product)' in source
    assert 'CommandHandler("music_suno_admin_test", cmd_music_suno_admin_test)' in source
    assert "has_admin_paid_confirmation(context)" in inspect.getsource(bot.cmd_tool_test_voice_tts_product)
    assert "has_admin_paid_confirmation(context)" in inspect.getsource(bot.cmd_music_suno_admin_test)
