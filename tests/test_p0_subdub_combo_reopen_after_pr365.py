import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import subdub_combo_blackbox


def test_combo_blackbox_normalizes_only_drifted_combo_final_state():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "process_type": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": "subtitle_plus_dub",
        "source_file_id": "video-file",
        "target_language": "Japanese",
        "voice_id": "female-voice",
        "voice_style": "female",
        "voice_speed": "1.0",
        "output_type": "video_subtitle",
        "output_format": "video_subtitle",
    }

    normalized = subdub_combo_blackbox.normalize_combo_state(state)

    assert normalized is not state
    assert normalized["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert normalized["process_type"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert normalized["video_processing_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert normalized["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert normalized["active_flow"] == "subtitle_plus_dub"
    assert normalized["product_type"] == "subtitle_dub"
    assert normalized["source_file_id"] == "video-file"
    assert normalized["target_language"] == "Japanese"
    assert normalized["voice_id"] == "female-voice"
    assert normalized["voice_style"] == "female"
    assert normalized["voice_speed"] == "1.0"
    assert normalized["output_type"] == "video_subtitle"
    assert normalized["output_format"] == "video_subtitle"


def test_combo_blackbox_leaves_subtitle_only_and_dub_only_states_untouched():
    for mode in (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, bot.VIDEO_SUBTITLE_MODE_DUB):
        state = {"mode": mode, "video_processing_mode": mode, "requested_mode": mode}
        assert subdub_combo_blackbox.normalize_combo_state(state) is state


def test_combo_callback_normalizes_before_existing_mp4_executor():
    source = inspect.getsource(bot.execute_subtitle_plus_dub_full_from_callback)

    assert "subdub_combo_blackbox.normalize_combo_state(state)" in source
    assert source.index("subdub_combo_blackbox.normalize_combo_state(state)") < source.index(
        "execute_video_dubbing_pipeline("
    )


def test_combo_callback_passes_normalized_state_to_existing_executor(monkeypatch):
    captured = {}

    async def fake_pipeline(_query, _context, state, _lang, **_kwargs):
        captured["state"] = state
        return {"ok": True, "mode": state["mode"]}

    async def fake_execute_engine(feature, params, context):
        captured["feature"] = feature
        captured["params_mode"] = params["mode"]
        captured["context"] = context
        return {"ok": True, "runner_result": await params["runner"]()}

    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_pipeline)
    monkeypatch.setattr(bot, "execute_engine", fake_execute_engine)
    query = SimpleNamespace(from_user=SimpleNamespace(id=42))
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": "subtitle_plus_dub",
    }

    result = asyncio.run(bot.execute_subtitle_plus_dub_full_from_callback(query, object(), state))

    assert result == {"ok": True, "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    assert captured["feature"] == "subtitle_plus_dub"
    assert captured["params_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert captured["state"]["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert captured["state"]["video_processing_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB


def test_combo_blackbox_does_not_own_pipeline_provider_or_delivery_code():
    source = inspect.getsource(subdub_combo_blackbox).lower()

    for forbidden in (
        "run_subdub_pipeline",
        "ffmpeg",
        "mux",
        "provider",
        "delivery",
        "shopaikey",
        "key4u",
    ):
        assert forbidden not in source
