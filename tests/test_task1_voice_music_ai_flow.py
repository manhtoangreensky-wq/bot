import inspect
from pathlib import Path

import bot
from providers.key4u_provider import Key4UConfig, Key4UProvider, join_provider_url, scoped_join_url


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def test_voice_menu_compact(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-shaonv")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-qn-qingse")
    assert _rows(bot.voice_hub_keyboard("vi")) == [
        ["✍️ Văn bản thành giọng nói", "🎧 Giọng nói thành văn bản"],
        ["👩 Giọng nữ", "👨 Giọng nam"],
        ["📂 Kho voice", "🎙 Tạo voice riêng"],
        ["⬅️ Studio âm thanh", "🏠 Menu chính"],
    ]


def test_music_menu_compact():
    assert _rows(bot.music_hub_keyboard("vi")) == [
        ["🎵 Tạo nhạc nền", "🎤 Bài hát có lời"],
        ["📂 Kho nhạc", "🎚 Cắt/ghép nhạc"],
        ["⬅️ Studio âm thanh", "🏠 Menu chính"],
    ]


def test_audio_studio_menu_compact():
    assert _rows(bot.music_tools_keyboard("vi")) == [
        ["🎙 Giọng đọc", "🎵 Nhạc"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]


def test_custom_voice_no_600_label():
    surfaces = "\n".join([
        bot.voice_clone_intro_text("vi"),
        bot.voice_profile_policy_label("vi"),
        bot.voice_clone_quote_text({"id": 1, "user_id": "1", "display_name": "Giọng thử"}, "vi"),
    ])
    assert "600 Xu" not in surfaces


def test_voice_profile_price_free_or_50(monkeypatch):
    monkeypatch.setattr(bot, "VOICE_PROFILE_FIRST_FREE", True)
    monkeypatch.setattr(bot, "VOICE_PROFILE_MAX_FREE_PER_USER", 1)
    monkeypatch.setattr(bot, "VOICE_PROFILE_PRICE_XU", 50)
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda *_args, **_kwargs: 0)
    assert bot.voice_profile_storage_price_xu(1) == 0
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda *_args, **_kwargs: 1)
    assert bot.voice_profile_storage_price_xu(1) == 50


def test_voice_clone_sample_sentence():
    assert bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT == "Cảm ơn bạn đã sử dụng trình nhân bản giọng nói của TOAN AAS."
    assert bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT in bot.voice_clone_sample_confirmation_text("vi")
    source = inspect.getsource(bot.handle_music_guided_pending_media)
    assert '"voice_clone_sample_confirm"' in source


def test_voice_clone_provider_guard_clean():
    text = bot.voice_clone_public_guard_text("vi")
    assert "TOAN AAS chưa xử lý" in text
    assert "chưa trừ Xu" in text
    for forbidden in ("MiniMax", "ShopAIKey", "API", "env", "provider"):
        assert forbidden not in text


def test_voice_provider_status_admin_only():
    source = inspect.getsource(bot.cmd_voice_status)
    assert "is_admin_user" in source
    status = bot.voice_status_text()
    assert "Voice clone missing" in status


def test_tool_test_minimax_tts_real_or_admin_blocker():
    source = inspect.getsource(bot.cmd_tool_test_minimax_tts)
    assert "is_admin_user" in source
    assert "missing_env" in source
    assert "shopaikey_minimax_tts_bytes" in source
    assert "send_audio" in source


def test_saved_voice_uses_real_voice_id():
    profile = {"provider_voice_id": "toanaas-real-voice-123", "status": "active"}
    assert bot.get_tts_voice_id("saved_voice", profile) == "toanaas-real-voice-123"
    source = inspect.getsource(bot.send_paid_saved_voice_tts_result)
    assert 'profile.get("provider_voice_id")' in source
    assert "spend_fixed_credit_info" in source
    assert source.index("execute_engine(") < source.index("spend_fixed_credit_info")


def test_voice_vault_number_select(monkeypatch):
    profile = {"id": 77, "status": "active", "provider_voice_id": "voice-77"}
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [profile])
    callbacks = _callbacks(bot.voice_vault_keyboard(9, "vi"))
    assert "music_quick|showroom|voice_profile_select_code:1" in callbacks
    monkeypatch.setattr(bot, "user_voice_profile_by_display_code", lambda _uid, code: profile if code == 1 else None)
    assert bot.user_voice_profile_by_display_code(9, 1)["provider_voice_id"] == "voice-77"


def test_failed_voice_not_usable():
    profile = {"id": 8, "status": "failed", "provider_voice_id": "bad-voice", "preview_audio_ref": "demo"}
    callbacks = _callbacks(bot.voice_profile_actions_keyboard(8, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile))
    assert bot.voice_profile_can_generate_tts(profile) is False
    assert not any("voice_profile_read:8" in callback for callback in callbacks)
    assert not any("voice_profile_default:8" in callback for callback in callbacks)


def test_voice_back_returns_previous_step(monkeypatch):
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [])
    assert "music_quick|showroom|voice_hub" in _callbacks(bot.voice_vault_keyboard(1, "vi"))
    assert "music_quick|showroom|voice_hub" in _callbacks(bot.voice_clone_keyboard("vi"))
    assert "music_quick|showroom|voice_clone_back_name:12" in _callbacks(bot.voice_clone_quote_keyboard(12, "vi"))
    source = inspect.getsource(bot.handle_music_quick_callback)
    assert 'previous_screen="voice_clone_sample_confirm"' in source
    assert 'return_to="voice_clone_sample_confirm"' in source


def test_music_background_guided_purpose_style_mood_duration():
    assert len(bot.MUSIC_GUIDED_PURPOSES) == 6
    assert len(bot.MUSIC_GUIDED_STYLES) == 7
    assert len(bot.MUSIC_GUIDED_MOODS) == 7
    assert [item[0] for item in bot.MUSIC_GUIDED_DURATIONS] == ["18s", "30s", "60s", "custom"]
    assert "music_quick|showroom|music_ai_back_purpose" in _callbacks(bot.music_guided_step_keyboard("style", "vi"))
    assert "music_quick|showroom|music_ai_back_style" in _callbacks(bot.music_guided_step_keyboard("mood", "vi"))
    assert "music_quick|showroom|music_ai_back_mood" in _callbacks(bot.music_guided_step_keyboard("duration", "vi"))


def test_music_background_guided_flow():
    test_music_background_guided_purpose_style_mood_duration()


def test_music_background_generates_three_options():
    options = bot.music_prompt_suggestions("nhạc nền bán hàng", 0, "vi", "guided")
    assert len(options) == 3
    assert [item["name"] for item in options] == [
        "Phương án 1: an toàn/dễ dùng",
        "Phương án 2: bán hàng/nổi bật",
        "Phương án 3: sáng tạo/khác biệt",
    ]


def test_music_background_three_options():
    test_music_background_generates_three_options()


def test_music_preview_6s_not_full_duration():
    result = {"guided_duration_seconds": 60, "music_ai_kind": "guided", "selected_prompt": "nhạc nền"}
    text = bot.music_ai_preview_text(result, "vi")
    assert "Thời lượng bản đầy đủ: <b>60 giây</b>" in text
    assert "Preview: <b>12 giây đầu</b>" in text
    callbacks = _callbacks(bot.music_ai_preview_keyboard("vi", result=result))
    assert "music_quick|showroom|music_ai_preview" in callbacks
    assert "music_quick|showroom|music_ai_confirm" in callbacks


def test_music_provider_guard_clean():
    text = bot.music_ai_public_guard_text("vi")
    assert "chưa trừ Xu" in text
    for forbidden in ("Suno", "Key4U", "ShopAIKey", "API", "env", "provider"):
        assert forbidden not in text


def test_song_seconds_full_guided_flow():
    assert _rows(bot.music_song_product_keyboard("vi"))[0] == ["🎤 Bài hát có lời AI"]
    assert "⏱ Theo số giây" not in _labels(bot.music_song_product_keyboard("vi"))
    assert "🎤 Bài hát có lời AI" in _labels(bot.music_song_product_keyboard("vi"))
    assert [item[0] for item in bot.MUSIC_SONG_GENRES] == ["pop", "ballad", "rap", "edm", "acoustic", "bolero", "custom"]
    assert "music_quick|showroom|song_back_topic" in _callbacks(bot.music_song_options_keyboard("genre", "vi"))
    assert "music_quick|showroom|song_back_genre" in _callbacks(bot.music_song_options_keyboard("mood", "vi"))
    assert "music_quick|showroom|song_back_mood" in _callbacks(bot.music_song_options_keyboard("vocal", "vi"))


def test_song_seconds_guided_flow():
    test_song_seconds_full_guided_flow()


def test_song_half_structure():
    text = bot.music_guided_description_from_result({
        "song_product": "half",
        "guided_purpose": "song",
        "guided_style": "pop",
        "guided_mood": "inspiring",
        "guided_duration": "60s",
    }, "vi")
    assert "nửa bài đủ lời" not in text.lower()
    assert "Bài hoàn chỉnh" in text
    assert "điệp khúc" in text


def test_song_full_price_half_plus_80_percent(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", False)
    monkeypatch.setattr(bot, "MUSIC_VOCAL_FULL_PRICE_XU", 500)
    assert bot.music_ai_output_price_xu(60, "song_half") == 500
    assert bot.music_ai_output_price_xu(120, "song_full") == 500


def test_song_no_nghe_xem_label():
    result = {"song_product": "full", "guided_duration_seconds": 120, "selected_prompt": "bài hát"}
    labels = _labels(bot.music_ai_preview_keyboard("vi", result=result))
    assert "▶️ Nghe thử 12 giây" in labels
    assert "✅ Dùng bản đầy đủ 800 Xu" in labels
    assert not any("nghe/xem" in label.lower() for label in labels)


def test_music_provider_status_admin_only():
    source = inspect.getsource(bot.cmd_music_provider_status)
    assert "is_admin_user" in source
    status = bot.music_status_text()
    assert "Selected endpoint" in status
    assert "Last submit smoke" in status
    assert "Last fetch smoke" in status
    assert "Last download smoke" in status
    assert "Last sanitized error" in status


def test_audio_provider_admin_commands_registered_and_guarded():
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    required = {
        "audio_provider_status": "cmd_provider_status",
        "voice_provider_status": "cmd_voice_status",
        "music_provider_status": "cmd_music_provider_status",
        "tool_test_voice_tts": "cmd_tool_test_minimax_tts",
        "tool_test_voice_clone": "cmd_tool_test_minimax_voice_clone",
        "tool_test_music_suno": "cmd_tool_test_key4u_suno",
        "audio_provider_curl": "cmd_audio_provider_curl",
    }
    for command, handler in required.items():
        assert f'CommandHandler("{command}", {handler})' in source
    assert "is_admin_user" in inspect.getsource(bot.cmd_audio_provider_curl)
    curl_text = bot.audio_provider_curl_text()
    assert "https://api.key4u.shop/minimax/v1/t2a_v2" in curl_text
    assert "https://api.key4u.shop/suno/submit/music" in curl_text
    assert "/minimax/v1/minimax/v1" not in curl_text
    assert "/suno/suno" not in curl_text


def test_audio_provider_status_shows_canonical_final_urls():
    voice_status = bot.voice_status_text()
    music_status = bot.music_status_text()
    assert "https://api.key4u.shop/minimax/v1/t2a_v2" in voice_status
    assert "https://api.key4u.shop/minimax/v1/files" in voice_status
    assert "https://api.key4u.shop/minimax/v1/voice_clone" in voice_status
    assert "https://api.key4u.shop/suno/submit/music" in music_status
    assert "https://api.key4u.shop/suno/fetch/{taskId}" in music_status


def test_shopaikey_tts_fallback_no_double_v1(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.com")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_ENDPOINT", "/tts/openai/speech")
    endpoint = bot.join_shopaikey_url(bot.SHOPAIKEY_TTS_BASE_URL, bot.SHOPAIKEY_TTS_ENDPOINT)
    assert endpoint == "https://api.shopaikey.com/tts/openai/speech"
    assert "/v1/v1/" not in endpoint
    source = inspect.getsource(bot.synthesize_standalone_tts_audio)
    assert "shopaikey_tts_public_smoke_ready()" in source
    assert "resolve_shopaikey_tts_audio_bytes" in inspect.getsource(bot.shopaikey_tts_bytes)
    assert "_download_audio_url_bytes" in inspect.getsource(bot.resolve_shopaikey_tts_audio_bytes)


def test_no_shopaikey_music_hardcode_without_smoke():
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    submit_source = inspect.getsource(bot.submit_music_generation_job)
    assert 'SHOPAIKEY_MUSIC_ENDPOINT = _env("SHOPAIKEY_MUSIC_ENDPOINT", "/submit/music")' in source
    assert 'SHOPAIKEY_MUSIC_STATUS_ENDPOINT = _env("SHOPAIKEY_MUSIC_STATUS_ENDPOINT", "/fetch/{taskId}")' in source
    assert '"/music/generations"' not in source
    assert "SUNO_REQUIRE_SMOKE_PASS" in submit_source
    assert "route_smoke not in smoke_pass_values" in submit_source
    assert "shopaikey_suno_final_url" in submit_source


def test_no_public_provider_terms_voice_music():
    surfaces = "\n".join([
        bot.voice_clone_public_guard_text("vi"),
        bot.standalone_tts_guard_text("vi"),
        bot.saved_voice_tts_confirm_text({"display_name": "Giọng riêng"}, "Xin chào", "normal", "vi"),
        bot.music_ai_public_guard_text("vi"),
        bot.get_suno_music_readiness()["safe_user_message"],
    ]).lower()
    for term in ("provider", "api", "key4u", "shopaikey", "minimax", "suno", "env", "ready=false", "traceback", "admin blocker"):
        assert term not in surfaces


def test_no_public_nghe_xem_combo():
    labels = "\n".join([
        "\n".join(_labels(bot.saved_voice_tts_confirm_keyboard(1, "vi"))),
        "\n".join(_labels(bot.music_ai_preview_keyboard("vi", result={"song_product": "full"}))),
    ]).lower()
    assert "nghe/xem" not in labels
    text = bot.music_ai_preview_text({"song_product": "full", "guided_duration_seconds": 120, "selected_prompt": "bài hát"}, "vi")
    assert "nghe/xem thử 1 lần trong 15 ngày" in text


def test_shopaikey_minimax_clone_payload_matches_documented_voice_id_rules():
    source = inspect.getsource(bot.shopaikey_minimax_voice_clone)
    assert 'r"[^A-Za-z0-9-]+"' in source
    assert '"language_boost": "auto"' in source
    assert '"aigc_watermark": False' in source


def test_shopaikey_suno_submit_and_fetch_match_documented_schema():
    submit = inspect.getsource(bot.submit_music_generation_job)
    poll = inspect.getsource(bot.poll_music_generation_job)
    payload_source = inspect.getsource(bot.shopaikey_suno_submit_payload)
    assert '"gpt_description_prompt": str(prompt or "")' in payload_source
    assert '"make_instrumental": bool(instrumental)' in payload_source
    assert '"duration": duration' not in submit
    assert "extract_shopaikey_suno_audio_urls" in poll
    assert "shopaikey_suno_final_url" in submit
    assert "shopaikey_suno_final_url" in poll


def test_key4u_voice_music_routes_match_reference():
    assert bot.KEY4U_BASE_URL == "https://api.key4u.shop"
    assert bot.KEY4U_MINIMAX_BASE_URL == "https://api.key4u.shop/minimax"
    assert bot.KEY4U_VOICE_BASE_URL == "https://voice.key4u.shop/api/v1"
    assert bot.KEY4U_SUNO_BASE_URL == "https://api.key4u.shop/suno"
    assert bot.KEY4U_TTS_ENDPOINT == "/v1/t2a_v2"
    assert bot.KEY4U_MINIMAX_TTS_ASYNC_ENDPOINT == "/v1/t2a_async_v2"
    assert bot.KEY4U_MINIMAX_TTS_QUERY_ENDPOINT == "/v1/query/t2a_async_query_v2"
    assert bot.KEY4U_MINIMAX_TTS_RETRIEVE_ENDPOINT == "/v1/files/retrieve"
    assert bot.KEY4U_MINIMAX_UPLOAD_ENDPOINT == "/v1/files"
    assert bot.KEY4U_MINIMAX_CLONE_ENDPOINT == "/v1/voice_clone"
    assert bot.KEY4U_SUNO_CREATE_ENDPOINT == "/submit/music"
    assert bot.KEY4U_SUNO_QUERY_ENDPOINT == "/fetch/{taskId}"
    assert bot.KEY4U_SUNO_LYRICS_ENDPOINT == "/submit/lyrics"
    assert bot.KEY4U_SUNO_WAV_ENDPOINT == "/act/wav/{clipId}"
    assert bot.KEY4U_SUNO_TIMING_ENDPOINT == "/act/timing/{clipId}"
    assert bot.KEY4U_TTS_MODEL
    assert bot.KEY4U_TTS_ALT_MODEL == "speech-2.6-hd"
    assert bot.KEY4U_MINIMAX_CLONE_MODEL == "speech-2.8-hd"
    assert bot.KEY4U_SUNO_MODEL


def test_key4u_audio_env_example_uses_canonical_scoped_urls():
    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "KEY4U_MINIMAX_BASE=https://api.key4u.shop/minimax" in env_example
    assert "KEY4U_TTS_ENDPOINT=/v1/t2a_v2" in env_example
    assert "KEY4U_MINIMAX_CLONE_ENDPOINT=/v1/voice_clone" in env_example
    assert "KEY4U_SUNO_BASE=https://api.key4u.shop/suno" in env_example
    assert "KEY4U_SUNO_CREATE_ENDPOINT=/submit/music" in env_example
    assert "KEY4U_SUNO_QUERY_ENDPOINT=/fetch/{taskId}" in env_example


def test_join_provider_url_no_v1_v1():
    assert bot.join_provider_url("https://api.key4u.shop/v1", "/v1/chat/completions") == "https://api.key4u.shop/v1/chat/completions"
    assert join_provider_url("https://api.key4u.shop/v1", "/v1/chat/completions") == "https://api.key4u.shop/v1/chat/completions"


def test_key4u_minimax_final_tts_url_exact():
    assert bot.key4u_minimax_final_url(bot.KEY4U_TTS_ENDPOINT) == "https://api.key4u.shop/minimax/v1/t2a_v2"


def test_key4u_minimax_no_duplicate_minimax_v1():
    cases = [
        ("https://api.key4u.shop/minimax", "/v1/t2a_v2"),
        ("https://api.key4u.shop", "/minimax/v1/t2a_v2"),
        ("https://api.key4u.shop/minimax/v1", "/t2a_v2"),
        ("https://api.key4u.shop/minimax/v1", "/minimax/v1/t2a_v2"),
    ]
    for base, endpoint in cases:
        url = join_provider_url(base, endpoint)
        assert url == "https://api.key4u.shop/minimax/v1/t2a_v2"
        assert "/minimax/v1/minimax/v1" not in url


def test_key4u_minimax_clone_urls_exact():
    assert bot.key4u_minimax_final_url(bot.KEY4U_MINIMAX_UPLOAD_ENDPOINT) == "https://api.key4u.shop/minimax/v1/files"
    assert bot.key4u_minimax_final_url(bot.KEY4U_MINIMAX_CLONE_ENDPOINT) == "https://api.key4u.shop/minimax/v1/voice_clone"


def test_key4u_suno_submit_url_exact():
    assert bot.key4u_suno_final_url(bot.KEY4U_SUNO_CREATE_ENDPOINT) == "https://api.key4u.shop/suno/submit/music"


def test_key4u_suno_fetch_url_exact():
    assert bot.key4u_suno_fetch_final_url("task-123") == "https://api.key4u.shop/suno/fetch/task-123"


def test_key4u_suno_no_duplicate_suno():
    cases = [
        ("https://api.key4u.shop/suno", "/submit/music"),
        ("https://api.key4u.shop", "/suno/submit/music"),
        ("https://api.key4u.shop/suno", "/suno/submit/music"),
        ("https://api.key4u.shop/suno/", "suno/fetch/task-123"),
    ]
    expected = [
        "https://api.key4u.shop/suno/submit/music",
        "https://api.key4u.shop/suno/submit/music",
        "https://api.key4u.shop/suno/submit/music",
        "https://api.key4u.shop/suno/fetch/task-123",
    ]
    for (base, endpoint), url in zip(cases, expected):
        joined = join_provider_url(base, endpoint)
        assert joined == url
        assert "/suno/suno" not in joined


def test_join_provider_url_absolute_endpoint():
    assert bot.join_provider_url("https://api.key4u.shop/suno", "https://example.com/path/") == "https://example.com/path"


def test_key4u_adapter_supports_scoped_voice_music_routes():
    assert scoped_join_url(
        "https://api.key4u.shop",
        "https://api.key4u.shop/minimax/v1",
        "/t2a_v2",
        "/minimax/v1",
    ) == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert scoped_join_url(
        "https://api.key4u.shop",
        "https://api.key4u.shop/suno",
        "/suno/submit/music",
        "/suno",
    ) == "https://api.key4u.shop/suno/submit/music"
    assert scoped_join_url(
        "https://api.key4u.shop",
        "https://api.key4u.shop/minimax/v1",
        "/minimax/v1/t2a_v2",
        "/minimax/v1",
    ) == "https://api.key4u.shop/minimax/v1/t2a_v2"
    provider = Key4UProvider(Key4UConfig(enabled=True, admin_smoke_enabled=True, api_key="sk-test"))
    capabilities = provider.list_capabilities()
    assert capabilities["tts_async"] == "needs_endpoint_docs"
    assert capabilities["voice_tts_fallback"] == "needs_endpoint_docs"
    source = inspect.getsource(Key4UProvider.suno_create)
    assert 'payload["prompt"] = lyrics_text[:4000]' in source
    assert 'payload["gpt_description_prompt"]' in source


def test_voice_music_provider_fallbacks_are_registered():
    tts_source = inspect.getsource(bot.synthesize_standalone_tts_audio)
    clone_source = inspect.getsource(bot.create_minimax_voice_profile_preview)
    music_source = inspect.getsource(bot.submit_music_generation_job)
    assert "shopaikey_minimax_tts_bytes" in tts_source
    assert "key4u_minimax_tts_bytes" in tts_source
    assert "voice_tts_fallback" in inspect.getsource(bot.key4u_minimax_tts_bytes)
    assert "shopaikey_minimax_upload_voice_sample" in clone_source
    assert "key4u_minimax_upload_voice_sample" in clone_source
    assert 'route_order = ["key4u_suno", "shopaikey_music"]' in music_source
    assert 'else ["shopaikey_music", "key4u_suno"]' in music_source
