import asyncio
from pathlib import Path

import bot


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_shopaikey_url_join_no_v1_v1():
    assert bot.join_shopaikey_url(
        "https://api.shopaikey.com/v1/",
        "/v1/video/generations",
    ) == "https://api.shopaikey.com/v1/video/generations"
    assert bot.join_shopaikey_url(
        "https://api.shopaikey.com/v1",
        "/audio/speech",
    ) == "https://api.shopaikey.com/v1/audio/speech"


def test_video_project_has_normalized_pipeline_fields(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_AI_PUBLIC_ENABLED", False)
    project = bot.build_video_project(
        991301,
        "trend",
        {
            "prompt": "A clean product reveal",
            "duration_seconds": 24,
            "video_tier": "standard",
            "aspect_ratio": "9:16",
            "music_option": "user_upload",
            "subtitle_option": "subtitle_original",
        },
    )
    required = {
        "project_id",
        "user_id",
        "source_flow",
        "flow_intent",
        "aspect_ratio",
        "duration_seconds",
        "segment_seconds",
        "segments",
        "processing_type",
        "quality_tier",
        "scenes",
        "script_text",
        "caption_text",
        "image_prompts",
        "video_prompts",
        "image_assets",
        "source_video_assets",
        "music_option",
        "music_source",
        "music_file_id",
        "music_prompt",
        "subtitle_option",
        "dubbing_option",
        "translation_enabled",
        "target_language",
        "voice_style",
        "price_preview",
        "provider_flags",
        "status",
        "created_at",
        "updated_at",
    }
    assert required.issubset(project)
    assert project["source_flow"] == "trend"
    assert project["duration_seconds"] == 24
    assert project["provider_flags"]["video_ai_public"] is False


def test_music_price_is_itemized_and_ai_guarded(monkeypatch):
    uploaded = bot.calculate_music_price(
        {"duration_seconds": 60, "music_option": "user_upload"}
    )
    assert uploaded["music_xu"] == bot.USER_UPLOAD_MUSIC_XU

    sfx = bot.calculate_music_price(
        {"duration_seconds": 60, "music_option": "sfx_library", "sfx_count": 2}
    )
    assert sfx["music_xu"] == max(
        bot.SFX_LIBRARY_MIN_XU,
        2 * bot.SFX_LIBRARY_XU_PER_ITEM,
    )

    monkeypatch.setattr(bot, "MUSIC_AI_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_ENABLED", False)
    monkeypatch.setattr(bot, "SHOPAIKEY_MUSIC_ENDPOINT", "")
    ai_music = bot.calculate_music_price(
        {"duration_seconds": 60, "music_option": "ai_music"}
    )
    assert ai_music["music_xu"] == 0
    assert ai_music["music_notes"]


def test_video_total_price_and_invoice_include_music():
    pricing = bot.calculate_video_total_price(
        24,
        "ai_text_to_video",
        "standard",
        "subtitle_original",
        "dub_original",
        False,
        music_option="user_upload",
    )
    assert pricing["base_video_xu"] == 1320
    assert pricing["addon_xu"] == 370
    assert pricing["music_xu"] == 0
    assert pricing["total_xu"] == 1690
    assert pricing["estimated_vnd"] == 169000

    text = bot.video_price_invoice_text({
        "current_video_duration_seconds": 24,
        "current_video_processing_type": "ai_text_to_video",
        "current_video_quality_tier": "standard",
        "current_video_subtitle_option": "subtitle_original",
        "current_video_dubbing_option": "dub_original",
        "current_video_music_option": "user_upload",
        "translation_enabled": False,
        "current_video_price_preview": pricing,
    })
    assert "Nhạc/SFX" in text
    assert "1.690 Xu" in text
    assert "169.000đ" in text


def test_finalization_payload_preserves_music_subtitle_and_dub():
    state = {
        "user_id": "991302",
        "source": "videoidea",
        "source_payload": {
            "prompt": "Premium commercial reveal",
            "duration_seconds": 24,
            "video_tier": "standard",
        },
        "video_finalization": {
            "music_enabled": True,
            "music_mode": "uploaded",
            "music_file_id": "music-file",
            "subtitle_enabled": True,
            "subtitle_mode": "manual",
            "subtitle_text": "TOAN AAS",
            "voice_enabled": True,
            "voice_mode": "tts",
            "voice_text": "TOAN AAS",
            "dub_enabled": True,
            "translation_enabled": False,
            "finalization_confirmed": True,
        },
    }
    payload = bot.video_finalization_payload(state)
    assert payload["music_option"] == "uploaded"
    assert payload["music_file_id"] == "music-file"
    assert payload["subtitle_option"] == "subtitle_original"
    assert payload["dubbing_option"] == "dub_original"
    assert payload["video_finalization_confirmed"] is True
    assert payload["video_project"]["music_option"] == "uploaded"


def test_quick_video_addon_entry_routes_to_music_step(monkeypatch):
    captured = {}

    async def fake_open(query, user_id, source, **kwargs):
        captured.update({
            "user_id": user_id,
            "source": source,
            **kwargs,
        })
        return "opened"

    monkeypatch.setattr(bot, "open_video_finalization", fake_open)
    result = asyncio.run(bot.start_video_addon_step(
        object(),
        991303,
        {
            "source": "promptvideo",
            "prompt": "A realistic product video",
            "duration_seconds": 8,
        },
        "low",
        "vi",
        source="ai",
    ))
    assert result == "opened"
    assert captured["source"] == "promptvideo"
    assert captured["source_payload"]["resume_video_addon"] is True
    assert captured["source_payload"]["video_tier"] == "low"


def test_music_and_addon_keyboards_have_real_callbacks():
    music_callbacks = _callbacks(bot.video_finalization_music_keyboard("vi"))
    assert {
        "vfinal|music_none",
        "vfinal|music_library",
        "vfinal|music_sfx",
        "vfinal|music_upload",
        "vfinal|music_ai",
    }.issubset(music_callbacks)
    addon_callbacks = _callbacks(bot.video_finalization_addon_keyboard("vi"))
    assert {
        "vfinal|addon_none",
        "vfinal|subtitle",
        "vfinal|voice",
        "vfinal|combo",
        "vfinal|translate_sub",
        "vfinal|translate_combo",
    }.issubset(addon_callbacks)


def test_provider_flags_and_admin_smoke_commands_are_guarded():
    source = Path(bot.__file__).resolve().read_text(encoding="utf-8")
    env_text = (Path(bot.__file__).resolve().parent / ".env.example").read_text(encoding="utf-8")
    for line in (
        "SHOPAIKEY_TTS_ENABLED=false",
        "SHOPAIKEY_MUSIC_ENABLED=false",
        "SHOPAIKEY_MUSIC_ENDPOINT=",
        "VIDEO_AI_PUBLIC_ENABLED=false",
        "XU_TO_VND=100",
    ):
        assert line in env_text
    assert 'CommandHandler("shopaikey_tts_test", cmd_tool_test_shopaikey_tts)' in source
    assert 'CommandHandler("shopaikey_music_test", cmd_shopaikey_music_test)' in source
    assert 'CommandHandler("shopaikey_music_job", cmd_shopaikey_music_job)' in source
    music_guard = source[
        source.index("async def cmd_shopaikey_music_test"):
        source.index("async def cmd_tool_test_shopaikey_image")
    ]
    assert "client.post" in music_guard
    assert "SHOPAIKEY_MUSIC_ENABLED" in music_guard
    assert "Không gọi provider và không trừ Xu." in music_guard
    assert "/suno/submit/music" in source
