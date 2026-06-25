import inspect

import bot


def source_between(source: str, start: str, end: str) -> str:
    start_idx = source.index(start)
    end_idx = source.index(end, start_idx)
    return source[start_idx:end_idx]


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def _closed_voice(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_clone_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "reason": "public gate closed"},
    )


def _closed_music(monkeypatch):
    readiness = {"ready": True, "public_enabled": False, "missing_env": [], "reason": "public gate closed"}
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: readiness)
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)


def _closed_subtitle(monkeypatch):
    def capability(_mode, _state=None, public=True):
        if public:
            return {"ok": False, "reason": "public_disabled", "missing": ["public_flag"]}
        return {"ok": True, "reason": "ready", "missing": []}

    monkeypatch.setattr(bot, "video_dubbing_capability", capability)
    monkeypatch.setattr(
        bot,
        "video_dubbing_configured_readiness",
        lambda *_args, **_kwargs: {"ok": True, "reason": "ready", "missing": []},
    )


def _closed_video(monkeypatch):
    def readiness(user_is_admin=False):
        if user_is_admin:
            return {"admin_ready": True, "public_ready": False, "missing_admin": [], "reason": "admin configured"}
        return {"admin_ready": False, "public_ready": False, "missing_public": ["public flag"], "reason": "public flag"}

    monkeypatch.setattr(bot, "get_video_prompt_export_readiness", readiness)


def test_voice_public_can_open_flow():
    source = inspect.getsource(bot.handle_music_quick_callback)
    block = source_between(source, 'if action == "voice_clone":', 'if action.startswith("voice_clone_back_upload:")')
    assert "voice_clone_access_allowed" not in block
    assert "voice_clone_provider_not_ready_public_text" not in block


def test_voice_public_can_enter_text_before_provider_guard(monkeypatch):
    _admin_only(monkeypatch)
    _closed_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "voice_clone", "draft", is_provider_call=False)
    assert decision["status"] == "allowed_public_draft"


def test_voice_public_provider_step_guarded_if_not_ready(monkeypatch):
    _admin_only(monkeypatch)
    _closed_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "voice_clone", "clone", is_provider_call=True)
    assert decision["status"] == "blocked_public_maintenance"
    assert decision["message"] == bot.PUBLIC_PRODUCT_MAINTENANCE_VI


def test_voice_admin_bypasses_public_gate(monkeypatch):
    _admin_only(monkeypatch)
    _closed_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "voice_clone", "clone", is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_voice_admin_paid_test_requires_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "voice_clone", "clone", is_provider_call=True, is_paid_job=True)
    assert decision["status"] == "blocked_admin_requires_confirm"


def test_voice_admin_paid_test_allowed_with_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_voice(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "voice_clone", "clone", is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_admin"


def test_music_public_can_open_flow(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "music", "menu", is_provider_call=False)
    assert decision["status"] == "allowed_public_draft"


def test_music_public_can_enter_song_request_before_guard(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    assert bot.music_ai_gate_keyboard(2, "vi") == bot.music_ai_preview_keyboard("vi")


def test_music_public_provider_step_guarded_if_not_ready(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "music", "submit", is_provider_call=True)
    assert decision["status"] == "blocked_public_maintenance"


def test_music_admin_bypasses_public_gate(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "music", "submit", is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_suno_admin_paid_test_requires_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "music", "submit", is_provider_call=True, is_paid_job=True)
    assert decision["status"] == "blocked_admin_requires_confirm"


def test_suno_admin_paid_test_allowed_with_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "music", "submit", is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_admin"


def test_admin_interactive_product_confirm_counts_as_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(
        1,
        "music",
        "submit",
        is_provider_call=True,
        is_paid_job=True,
        admin_interactive_confirm=True,
    )
    assert decision["status"] == "allowed_admin"
    assert decision["reason"] == "admin interactive product confirmation"


def test_subtitle_public_can_open_flow():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    block = source_between(source, 'if action in {"type", "studio", "showroom"}:', 'mode = normalize_video_translate_mode(')
    assert "video_dubbing_public_processing_ready" not in block
    assert "video_dubbing_guard_text" not in block


def test_subtitle_public_can_select_language_before_guard():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    block = source_between(source, 'if action == "output":', 'if action == "continue_dubbing":')
    assert "video_dubbing_public_processing_ready" not in block
    assert "preview_guarded" not in block


def test_subtitle_public_processing_guarded_if_not_ready(monkeypatch):
    _admin_only(monkeypatch)
    _closed_subtitle(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "subtitle_auto", bot.VIDEO_SUBTITLE_MODE_CREATE, is_provider_call=True)
    assert decision["status"] == "blocked_public_maintenance"


def test_subtitle_admin_bypasses_public_gate(monkeypatch):
    _admin_only(monkeypatch)
    _closed_subtitle(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "subtitle_auto", bot.VIDEO_SUBTITLE_MODE_CREATE, is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_dub_admin_paid_test_requires_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_subtitle(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "video_dub", bot.VIDEO_SUBTITLE_MODE_DUB, is_provider_call=True, is_paid_job=True)
    assert decision["status"] == "blocked_admin_requires_confirm"


def test_dub_admin_paid_test_allowed_with_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_subtitle(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "video_dub", bot.VIDEO_SUBTITLE_MODE_DUB, is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_admin"


def test_dub_admin_interactive_confirm_counts_as_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_subtitle(monkeypatch)
    decision = bot.video_dubbing_engine_access_decision(
        1,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        {},
        is_paid_job=True,
        admin_interactive_confirm=True,
    )
    assert decision["status"] == "allowed_admin_configured"


def test_video_public_can_reach_invoice_before_guard(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "video", "invoice", is_provider_call=False)
    assert decision["status"] == "allowed_public_draft"


def test_video_public_export_guarded_if_engine_not_ready(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "video", "export", is_provider_call=True)
    assert decision["status"] == "blocked_public_maintenance"


def test_video_admin_bypasses_public_video_gate(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "video", "export", is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_multiscene_admin_bypasses_public_gate(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "video_multiscene_stitching_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_queue_available", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_scene_tested", lambda _scene_count: True)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": True})
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _scene_count: False)
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_URL", "https://example.test/video")
    monkeypatch.setattr(bot, "SHOPAIKEY_VIDEO_MODEL", "model")
    decision = bot.can_user_access_product_engine(1, "video_multiscene", "3", is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_long_video_admin_bypasses_public_gate(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_LONG_RENDER_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_LONG_AI_PUBLIC_ENABLED", False)
    decision = bot.can_user_access_product_engine(1, "long_video", "render", is_provider_call=True)
    assert decision["status"] == "allowed_admin"


def test_video_admin_paid_test_requires_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "video", "export", is_provider_call=True, is_paid_job=True)
    assert decision["status"] == "blocked_admin_requires_confirm"


def test_video_admin_paid_test_allowed_with_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(1, "video", "export", is_provider_call=True, is_paid_job=True, confirm_paid=True)
    assert decision["status"] == "allowed_admin"


def test_video_admin_interactive_confirm_counts_as_confirm_paid(monkeypatch):
    _admin_only(monkeypatch)
    _closed_video(monkeypatch)
    decision = bot.can_user_access_product_engine(
        1,
        "video",
        "export",
        is_provider_call=True,
        is_paid_job=True,
        admin_interactive_confirm=True,
    )
    assert decision["status"] == "allowed_admin"


def test_public_provider_step_guarded(monkeypatch):
    _admin_only(monkeypatch)
    _closed_music(monkeypatch)
    decision = bot.can_user_access_product_engine(2, "music", "provider", is_provider_call=True)
    assert decision["message"] == bot.PUBLIC_PRODUCT_MAINTENANCE_VI


def test_admin_paid_tests_require_confirm():
    source = inspect.getsource(bot)
    for name in (
        "cmd_tool_test_minimax_tts",
        "cmd_tool_test_minimax_voice_clone",
        "cmd_tool_test_key4u_suno",
        "cmd_tool_test_music_ai",
        "run_admin_video_pipeline_smoke",
        "cmd_tool_test_shopaikey_video",
        "cmd_tool_test_key4u_video",
        "cmd_tool_test_key4u_video_model",
    ):
        block = source_between(source, f"async def {name}", "\nasync def ")
        assert "has_admin_paid_confirmation" in block
        assert "no provider call" in block


def test_product_callbacks_do_not_render_admin_paid_smoke_warning():
    music_source = inspect.getsource(bot.handle_music_quick_callback)
    music_product_block = source_between(music_source, 'if action in {"music_ai_guard", "music_ai_preview"}:', 'if action == "music_ai_status":')
    assert "admin_paid_confirm_required_text" not in music_product_block
    assert "admin_interactive_confirm=True" in music_product_block

    dub_source = inspect.getsource(bot.handle_video_dubbing_callback)
    dub_product_block = source_between(dub_source, "confirm_modes = {", "return await safe_edit_or_send(query, video_dubbing_menu_text")
    assert "admin_paid_confirm_required_text" not in dub_product_block
    assert "admin_interactive_confirm=True" in dub_product_block


def test_no_fake_success_public_progress_copy():
    text = bot.video_dubbing_job_progress_text("Tạo phụ đề tự động", 1234, "vi")
    assert "đã tạo xong" not in text.lower()
    assert "hàng chờ" not in text.lower()
    assert "Mã job" not in text
    assert "Tác vụ:" not in text


def test_public_no_provider_task_job_text():
    public_texts = [
        bot.PUBLIC_PRODUCT_MAINTENANCE_VI,
        bot.music_ai_public_guard_text("vi"),
        bot.voice_clone_public_guard_text("vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False),
        bot.video_dubbing_job_progress_text("Tạo phụ đề tự động", 1234, "vi"),
    ]
    joined = "\n".join(public_texts).lower()
    for token in ("provider", "api", "task_id", "job id", "mã job", "debug"):
        assert token not in joined


def test_public_guard_no_charge():
    text = bot.PUBLIC_PRODUCT_MAINTENANCE_VI
    assert "chưa trừ Xu" in text
    assert "chưa xử lý" in text


def test_admin_status_commands_admin_only():
    source = inspect.getsource(bot)
    for name in ("cmd_voice_engine_status", "cmd_music_engine_status", "cmd_subtitle_engine_status", "cmd_video_engine_status"):
        block = source_between(source, f"async def {name}", "\nasync def ")
        assert "is_admin_user" in block


def test_admin_status_no_secrets():
    text = "\n".join(
        bot.voice_engine_status_lines()
        + bot.music_engine_status_lines()
        + bot.subtitle_engine_status_lines()
        + bot.video_engine_status_lines()
    ).lower()
    for token in ("sk-", "bearer ", "api_key=", "token="):
        assert token not in text


def test_required_admin_alias_commands_registered():
    source = inspect.getsource(bot)
    assert 'CommandHandler("tool_test_suno_song", cmd_tool_test_key4u_suno)' in source
    assert 'CommandHandler("tool_test_subtitle_auto", cmd_tool_test_subtitle_generate)' in source
