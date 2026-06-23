import asyncio
import inspect

import bot


def _admin_only(monkeypatch, admin_id=1):
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: str(uid) == str(admin_id))


def test_execute_engine_blocks_missing_adapter_without_fake_success(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"ready": False, "public_enabled": False, "missing_env": ["SUNO_API_KEY"], "reason": "missing"},
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

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
            },
        )
    )

    assert result["ok"] is False
    assert result["status"] == "GATE_BLOCKED"
    assert result.get("job_created") is not True
    assert "music_song adapter" in result["message"]
    assert bot.ADMIN_PAID_CONFIRM_FLAG not in result["message"]


def test_execute_engine_voice_requires_output_bytes(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_minimax_voice_readiness",
        lambda: {"ready": True, "public_enabled": True, "missing_env": [], "reason": "ready"},
    )

    async def empty_tts(*_args, **_kwargs):
        return True, b"", "empty_audio"

    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", empty_tts)
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

    assert result["ok"] is False
    assert result["status"] == "NO_OUTPUT_BYTES"


def test_slash_smoke_requires_confirm_but_interactive_product_does_not(monkeypatch):
    _admin_only(monkeypatch)
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"ready": True, "public_enabled": False, "missing_env": [], "reason": "public gate closed"},
    )
    monkeypatch.setattr(bot, "music_ai_public_processing_ready", lambda _readiness=None: False)

    smoke = bot.evaluate_engine_gate(
        "music_song",
        {"result": {"song_product": "half"}},
        {"user_id": 1, "entry_source": bot.ENGINE_ENTRY_SOURCE_SLASH_SMOKE, "confirm_paid": False, "is_paid_job": True},
    )
    product = bot.evaluate_engine_gate(
        "music_song",
        {"result": {"song_product": "half"}},
        {
            "user_id": 1,
            "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
            "confirm_paid": True,
            "admin_interactive_confirm": True,
            "is_paid_job": True,
        },
    )

    assert smoke["status"] == "blocked_admin_requires_confirm"
    assert bot.ADMIN_PAID_CONFIRM_FLAG in smoke["message"]
    assert product["status"] == "allowed_admin"
    assert bot.ADMIN_PAID_CONFIRM_FLAG not in product["message"]


def test_product_and_smoke_sources_use_shared_executor():
    assert 'execute_engine(\n        "voice_tts"' in inspect.getsource(bot.send_standalone_tts_result)
    assert 'execute_engine(\n        "voice_saved_tts"' in inspect.getsource(bot.send_paid_saved_voice_tts_result)
    music_source = inspect.getsource(bot.handle_music_quick_callback)
    assert "music_engine_feature_for_result(result)" in music_source
    assert "execute_engine(" in music_source
    assert "execute_engine(" in inspect.getsource(bot.cmd_tool_test_music_ai)
    assert "execute_engine(" in inspect.getsource(bot.run_admin_video_pipeline_smoke)
    assert "execute_engine(" in inspect.getsource(bot.handle_video_export_confirm)
    assert "execute_engine(" in inspect.getsource(bot.handle_video_dubbing_callback)


def test_song_package_confirm_label_does_not_use_seconds():
    half = bot.music_confirm_product_label({"song_product": "half", "guided_duration_seconds": 60}, "vi")
    full = bot.music_confirm_product_label({"song_product": "full", "guided_duration_seconds": 120}, "vi")
    seconds = bot.music_confirm_product_label({"song_product": "seconds", "guided_duration_seconds": 30}, "vi")

    assert "giây" not in half
    assert "giây" not in full
    assert "30 giây" in seconds


def test_global_clear_removes_voice_music_subtitle_video_pending():
    uid = "engine-remap-v2"
    bot.USER_PENDING[bot.product_context_key(uid)] = {"type": "product_context"}
    bot.USER_PENDING[bot.music_guided_pending_key(uid)] = {"type": "music_guided"}
    bot.USER_PENDING[bot.video_dubbing_pending_key(uid)] = {"type": "video_dubbing"}
    bot.USER_PENDING[bot.video_finalization_pending_key(uid)] = {"type": "video_finalization"}

    assert bot.clear_pending_start_notice(uid)
    assert bot.product_context_key(uid) not in bot.USER_PENDING
    assert bot.music_guided_pending_key(uid) not in bot.USER_PENDING
    assert bot.video_dubbing_pending_key(uid) not in bot.USER_PENDING
    assert bot.video_finalization_pending_key(uid) not in bot.USER_PENDING
