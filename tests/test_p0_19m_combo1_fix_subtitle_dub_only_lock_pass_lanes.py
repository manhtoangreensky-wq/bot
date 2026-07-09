import bot


def test_combo_final_video_state_forces_mp4_after_translated_subtitle():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "process_type": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "output_type": "srt",
        "output_format": "srt",
        "translated_subtitle_ref": "video_dubbing_artifact:1:translated_srt",
        "target_language": "日本語",
        "voice_style": "Giọng nữ",
    }

    fixed = bot.subdub_combo_final_video_state(state)

    assert fixed["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert fixed["process_type"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert fixed["video_processing_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert fixed["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert fixed["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB
    assert fixed["output_type"] == "video_subtitle"
    assert fixed["output_format"] == "mp4"
    assert fixed["translated_subtitle_ref"] == "video_dubbing_artifact:1:translated_srt"
    assert fixed["target_language"] == "日本語"
    assert fixed["voice_style"] == "Giọng nữ"
    assert fixed["combo_final_video_locked"] is True


def test_combo_requires_final_mp4_after_state_normalization():
    state = bot.subdub_combo_final_video_state({
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "output_type": "srt",
        "output_format": "srt",
        "source_mime_type": "video/mp4",
    })

    assert bot.subdub_mode_requires_final_video(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state,
        "video/mp4",
        state["output_type"],
    ) is True


def test_combo_state_accepts_alias_mode_without_touching_target_voice():
    state = bot.subdub_combo_final_video_state({
        "mode": "subtitle_dub_video",
        "target_language": "ja",
        "voice_id": "female-real-voice",
        "voice_style": "Giọng nữ",
        "voice_speed": "1.0",
    })

    assert state["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert state["target_language"] == "ja"
    assert state["voice_id"] == "female-real-voice"
    assert state["voice_style"] == "Giọng nữ"
    assert state["voice_speed"] == "1.0"


def test_subtitle_only_state_is_not_touched():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "output_type": "burn",
        "output_format": "burn",
        "active_flow": "subtitle_translate",
    }

    assert bot.subdub_combo_final_video_state(state) == state


def test_dub_only_state_is_not_touched():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "output_type": "video",
        "output_format": "video",
        "voice_style": "Giọng nữ",
    }

    assert bot.subdub_combo_final_video_state(state) == state

