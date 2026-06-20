import inspect
import asyncio

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_video_voice_profile_uses_free_50_policy_not_600(monkeypatch):
    monkeypatch.setattr(bot, "active_voice_profile_count", lambda *_args, **_kwargs: 0)
    assert bot.voice_profile_storage_price_xu(123, bot.PRODUCT_CONTEXT_VIDEO_ADDON, 0) == 0

    monkeypatch.setattr(bot, "active_voice_profile_count", lambda *_args, **_kwargs: 1)
    assert bot.voice_profile_storage_price_xu(123, bot.PRODUCT_CONTEXT_VIDEO_ADDON, 0) == bot.VOICE_PROFILE_PRICE_XU == 50

    public_text = "\n".join([
        bot.video_finalization_voice_text({}, "vi"),
        "\n".join(_labels(bot.video_finalization_voice_keyboard("vi"))),
        bot.voice_clone_quote_text({"id": 10, "user_id": "123", "display_name": "Test"}, "vi", bot.PRODUCT_CONTEXT_VIDEO_ADDON),
    ])
    assert "+600 Xu" not in public_text
    assert "600 Xu" not in public_text
    assert "50" in public_text
    assert bot.video_addon_pricing_matrix()["voice_clone_create"]["price_xu"] == 50


def test_minimax_tts_delegates_to_direct_route_when_proxy_missing(monkeypatch):
    captured = {}

    async def fake_direct(text, voice_id="", voice_style=""):
        captured.update({"text": text, "voice_id": voice_id, "voice_style": voice_style})
        return "PASS", b"audio-bytes", "direct", 200

    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "MINIMAX_API_KEY", "direct-key")
    monkeypatch.setattr(bot, "MINIMAX_GROUP_ID", "group-1")
    monkeypatch.setattr(bot, "MINIMAX_TTS_MODEL", "speech-02-hd")
    monkeypatch.setattr(bot, "direct_minimax_tts_bytes", fake_direct)

    assert bot.minimax_tts_configured() is True
    status, audio, detail, http_status = asyncio.run(bot.shopaikey_minimax_tts_bytes("xin chao", voice_id="female-real"))

    assert (status, audio, detail, http_status) == ("PASS", b"audio-bytes", "direct", 200)
    assert captured["voice_id"] == "female-real"


def test_200_xu_tier_allows_default_export_without_paid_addons():
    state = {
        "video_tier": "low",
        "current_video_duration_seconds": 24,
        "video_project": {"scene_count": 3},
        "current_video_subtitle_option": "none",
        "current_video_dubbing_option": "none",
        "current_video_music_option": "none",
        "current_video_voice_choice": "default_female",
    }

    assert bot.validate_video_tier_selection(state, "low")["ok"] is True

    blocked = bot.validate_video_tier_selection({**state, "current_video_subtitle_option": "subtitle_original"}, "low")
    assert blocked["blocked"] is True
    assert "subtitle" in blocked["reasons"]

    blocked = bot.validate_video_tier_selection({**state, "paid_extra_duration": True}, "low")
    assert blocked["blocked"] is True
    assert "extra_duration" in blocked["reasons"]

    cleaned = bot.clear_video_paid_addons_from_state({**state, "current_video_subtitle_option": "subtitle_original", "current_video_music_choice": "ai_music"})
    assert cleaned["current_video_subtitle_option"] == "none"
    assert cleaned["current_video_music_choice"] == "none"


def test_export_ai_opens_addons_before_package():
    source = inspect.getsource(bot.handle_video_finalization_callback)
    export_block = source.split('if action in {"export_local", "export_ai"}:', 1)[1].split('if action == "save":', 1)[0]

    assert "video_finalization_menu_text" in export_block
    assert export_block.index("video_finalization_menu_text") < export_block.index("video_finalization_tier_text")


def test_voice_vault_uses_dynamic_number_codes(monkeypatch):
    rows = [
        {"id": 90, "display_name": "Voice A", "status": "active", "is_default": 0},
        {"id": 80, "display_name": "Voice B", "status": "active", "is_default": 1},
    ]

    monkeypatch.setattr(bot, "user_voice_profile_count", lambda _uid: 7)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda _uid, _limit=8, _offset=0, include_inactive=True: rows)

    callbacks = _callbacks(bot.voice_vault_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, page=1))

    assert bot.voice_profile_display_code(1, 0, 5) == 6
    assert "music_quick|showroom|voice_profile_select_code:6" in callbacks
    assert "music_quick|showroom|voice_profile_select:90" not in callbacks


def test_failed_voice_profile_cannot_be_used_or_defaulted():
    profile = {"id": 5, "status": "failed", "display_name": "Failed", "provider_voice_id": "bad"}

    showroom_callbacks = _callbacks(bot.voice_profile_actions_keyboard(5, "vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile))
    video_callbacks = _callbacks(bot.voice_profile_actions_keyboard(5, "vi", bot.PRODUCT_CONTEXT_VIDEO_ADDON, profile))

    joined = "\n".join(showroom_callbacks + video_callbacks)
    assert "voice_profile_default:5" not in joined
    assert "voice_profile_read:5" not in joined
    assert "voice_profile_use:5" not in joined
    assert "voice_profile_rename:5" in joined
    assert "voice_profile_delete:5" in joined


def test_dubbing_voice_selection_passes_voice_id_to_minimax(monkeypatch):
    captured = {}

    async def fake_minimax(text, voice_id="", voice_style=""):
        captured.update({"text": text, "voice_id": voice_id, "voice_style": voice_style})
        return "PASS", b"audio-bytes", "ok", 200

    monkeypatch.setattr(bot, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(bot, "key4u_minimax_tts_public_ready", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_public_ready", lambda: True)
    monkeypatch.setattr(bot, "direct_minimax_tts_public_ready", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_tts_fallback_public_ready", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", fake_minimax)

    labels = _labels(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    callbacks = _callbacks(bot.video_dubbing_voice_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert "👩 Giọng nữ" in labels
    assert "👨 Giọng nam" in labels
    assert "📂 Kho voice" in labels
    assert "videodub|voice|default_female" in callbacks
    assert "videodub|voice_saved" in callbacks

    _provider, audio, _detail = asyncio.run(bot.video_dubbing_tts_bytes("xin chao", "giọng nữ", "female-id-1"))
    assert audio == b"audio-bytes"
    assert captured["voice_id"] == "female-id-1"


def test_dubbing_confirm_shows_voice_text_pricing():
    text = bot.video_dubbing_confirm_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "video_file_id": "video-1",
            "video_duration": 383,
            "target_language": "Tiếng Anh",
            "voice_style": "giọng nữ mặc định",
        },
        "vi",
    )

    assert "Tạo phụ đề" in text
    assert "Dịch phụ đề" in text
    assert "Tạo giọng lồng tiếng" in text
    assert "Ghép audio/video" in text
    assert "Tổng Xu" in text
