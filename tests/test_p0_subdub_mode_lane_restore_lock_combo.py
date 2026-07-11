import asyncio

import bot
from services import subdub_blackboxes


def _video_state(mode: str, **overrides):
    state = {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "requested_mode": "subtitle_plus_dub",
        "active_flow": "subtitle_translate" if mode == "subtitle_translate" else "dub_audio",
        "product": "subtitle_plus_dubbing",
        "product_type": "subtitle_dub",
        "output_type": "video_subtitle",
        "output_format": "video_subtitle",
        "video_file_id": "telegram-video",
        "source_mime_type": "video/mp4",
        "target_language": "Tiếng Việt",
        "voice_id": "female-voice",
        "translate_requested": "1",
    }
    state.update(overrides)
    return state


def test_subtitle_only_clears_stale_combo_route_keys():
    normalized = subdub_blackboxes.normalize_standalone_video_lane_entry_state(
        _video_state("subtitle_translate")
    )

    assert normalized["requested_mode"] == "subtitle_translate"
    assert normalized["active_flow"] == "subtitle_translate"
    assert normalized["product_type"] == "subtitle_only"
    assert normalized["output_type"] == "burn"
    assert bot.subdub_resolved_route_mode("", normalized) == "subtitle_translate"


def test_dub_only_clears_stale_combo_route_keys_without_losing_voice():
    normalized = subdub_blackboxes.normalize_standalone_video_lane_entry_state(
        _video_state("dub")
    )

    assert normalized["requested_mode"] == "dub"
    assert normalized["active_flow"] == "dub_audio"
    assert normalized["product_type"] == "dub_only"
    assert normalized["output_type"] == "video"
    assert normalized["voice_id"] == "female-voice"
    assert normalized["target_language"] == "Tiếng Việt"
    assert normalized["translate_requested"] == "1"
    assert bot.subdub_resolved_route_mode("", normalized) == "dub"


def test_real_combo_state_is_byte_for_byte_unchanged():
    combo = _video_state(
        "subtitle_translate",
        active_flow="subtitle_plus_dub",
        requested_mode="subtitle_plus_dub",
        product_type="subtitle_dub",
    )

    normalized = subdub_blackboxes.normalize_standalone_video_lane_entry_state(combo)

    assert normalized is combo
    assert normalized == combo
    assert bot.subdub_resolved_route_mode("", normalized) == "subtitle_plus_dub"


def test_each_lane_runner_receives_only_its_canonical_state():
    received = {}

    async def runner(**kwargs):
        received.update(kwargs["state"])
        return {"ok": True}

    result = asyncio.run(
        subdub_blackboxes.run_subdub_lane_blackbox(
            lane_mode="subtitle_translate",
            runner=runner,
            mode="subtitle_translate",
            state=_video_state("subtitle_translate"),
        )
    )

    assert result["ok"] is True
    assert received["requested_mode"] == "subtitle_translate"
    assert received["active_flow"] == "subtitle_translate"
    assert received["output_type"] == "burn"


def test_file_translation_state_is_not_rewritten_as_video():
    state = {
        "mode": "subtitle_translate",
        "active_flow": "subtitle_file_translate",
        "source_media_type": "subtitle_file",
        "source_mime_type": "text/plain",
        "output_type": "srt",
    }

    normalized = subdub_blackboxes.normalize_standalone_video_lane_entry_state(state)

    assert normalized is state
    assert normalized["output_type"] == "srt"
