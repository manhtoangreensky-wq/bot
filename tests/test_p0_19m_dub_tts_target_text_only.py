import asyncio

import bot


SOURCE_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "女主的选角米妮阿尔科克\n"
)

TRANSLATED_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "Diễn viên nữ chính là Milly Alcock\n"
)


async def _fake_translate_subtitle_segments(segments, target_language, **_kwargs):
    assert target_language == "Tiếng Việt"
    assert segments[0]["text"] == "女主的选角米妮阿尔科克"
    return {
        "segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Diễn viên nữ chính là Milly Alcock"}],
        "srt": TRANSLATED_SRT,
        "provider": "unit",
    }


def _state_for_mode(uid, mode):
    bot.clear_video_dubbing_pending(uid)
    ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", SOURCE_SRT)
    return bot.set_video_dubbing_pending(
        uid,
        "processing",
        mode=mode,
        process_type=mode,
        video_processing_mode=mode,
        requested_mode=mode,
        source_subtitle_ref=ref,
        subtitle_ref=ref,
        target_language="Tiếng Việt",
        translate_requested="0",
        source_mime_type="text/plain",
        video_duration=2,
    )


def test_dub_only_tts_uses_translated_text_even_when_translate_flag_is_stale(monkeypatch):
    uid = 190091
    monkeypatch.setattr(bot, "translate_subtitle_segments", _fake_translate_subtitle_segments)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            _state_for_mode(uid, bot.VIDEO_SUBTITLE_MODE_DUB),
            uid,
        )
    )

    assert prepared["translation_provider"] == "unit"
    assert prepared["output_segments"][0]["text"] == "Diễn viên nữ chính là Milly Alcock"
    assert "女主" not in prepared["output_script"]


def test_combo_tts_uses_translated_text_even_when_translate_flag_is_stale(monkeypatch):
    uid = 190092
    monkeypatch.setattr(bot, "translate_subtitle_segments", _fake_translate_subtitle_segments)

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            None,
            _state_for_mode(uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
            uid,
        )
    )

    assert prepared["translation_provider"] == "unit"
    assert prepared["output_segments"][0]["text"] == "Diễn viên nữ chính là Milly Alcock"
    assert "女主" not in prepared["output_script"]


def test_original_target_keeps_source_text_when_explicitly_requested(monkeypatch):
    uid = 190093
    called = False

    async def forbidden_translate(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("source/original target must not translate")

    monkeypatch.setattr(bot, "translate_subtitle_segments", forbidden_translate)
    state = {
        **_state_for_mode(uid, bot.VIDEO_SUBTITLE_MODE_DUB),
        "target_language": "original",
        "translate_requested": "0",
    }

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(None, state, uid))

    assert called is False
    assert prepared["output_segments"][0]["text"] == "女主的选角米妮阿尔科克"
