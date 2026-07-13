import asyncio
import inspect

import bot


SOURCE_SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n\n"
    "2\n00:00:01,500 --> 00:00:03,000\nTam biet\n"
)


def _state_with_source(uid: int, target: str = "English") -> dict:
    bot.clear_video_dubbing_pending(uid)
    source_ref = bot.set_video_dubbing_artifact(uid, "source_subtitle", SOURCE_SRT)
    return bot.set_video_dubbing_pending(
        uid,
        "processing",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        subtitle_ref=source_ref,
        source_subtitle_ref=source_ref,
        source_mime_type="text/plain",
        target_language=target,
        translate_requested="1",
    )


def test_target_language_change_invalidates_old_translation_artifact():
    uid = 990_701
    try:
        state = _state_with_source(uid, "Tiếng Việt")
        translated_ref = bot.set_video_dubbing_artifact(uid, "translated_subtitle", SOURCE_SRT)
        state = bot.set_video_dubbing_pending(
            uid,
            "processing",
            translated_subtitle_ref=translated_ref,
            translated_subtitle_target_language="vi",
            translated_subtitle_source_hash=bot.subdub_translation_cache_source_hash(SOURCE_SRT),
        )
        changed = bot.set_video_dubbing_pending(uid, "language", target_language="English")

        assert state["translated_subtitle_ref"] == translated_ref
        assert changed["translated_subtitle_ref"] == ""
        assert changed["translated_subtitle_target_language"] == ""
        assert changed["translated_subtitle_source_hash"] == ""
    finally:
        bot.clear_video_dubbing_pending(uid)


def test_prepare_subtitles_reuses_cache_only_for_same_source_and_language(monkeypatch):
    uid = 990_702
    calls = []

    async def fake_translate(segments, target_language, **_kwargs):
        calls.append(target_language)
        translated = [
            {**dict(item), "text": f"EN-{index}"}
            for index, item in enumerate(segments, start=1)
        ]
        return {
            "segments": translated,
            "provider": "fixture",
            "srt": bot.video_dubbing_srt_from_segments(translated),
        }

    monkeypatch.setattr(bot, "translate_subtitle_segments", fake_translate)
    try:
        state = _state_with_source(uid, "English")
        stale_ref = bot.set_video_dubbing_artifact(uid, "translated_subtitle", "stale Vietnamese")
        state = bot.set_video_dubbing_pending(
            uid,
            "processing",
            translated_subtitle_ref=stale_ref,
            translated_subtitle_target_language="vi",
            translated_subtitle_source_hash=bot.subdub_translation_cache_source_hash(SOURCE_SRT),
        )

        first = asyncio.run(bot.video_dubbing_prepare_subtitles(None, state, uid))
        assert calls == ["English"]
        assert first["translation_cache_hit"] is False
        assert "EN-1" in first["output_subtitle"]

        second = asyncio.run(bot.video_dubbing_prepare_subtitles(None, first["state"], uid))
        assert calls == ["English"]
        assert second["translation_cache_hit"] is True
        assert second["output_subtitle"].strip() == first["output_subtitle"].strip()
    finally:
        bot.clear_video_dubbing_pending(uid)


def test_custom_translation_target_never_silently_becomes_vietnamese():
    assert bot.resolve_translate_target("Italiano") == "Italiano"
    assert bot.translate_target_label("Italiano") == "Italiano"
    source = inspect.getsource(bot.translate_subtitle_text)
    assert "target_label = translate_target_label(target)" in source
    assert "Translate the subtitle text to natural {target_label}" in source


def test_missing_translation_marker_survives_cue_lock_and_never_becomes_target_tts(monkeypatch):
    calls = 0

    async def fake_translate(text, _target, **_kwargs):
        nonlocal calls
        calls += 1
        return {"text": "Hello" if calls == 1 else "", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    source = bot.video_dubbing_segments_from_subtitle(SOURCE_SRT)
    translated = asyncio.run(bot.translate_subtitle_segments(source, "English"))

    assert translated["translation_missing_count"] == 1
    assert translated["segments"][1]["translate_missing"] is True
    policy = __import__(
        "services.subtitle_dub_product_pipeline",
        fromlist=["resolve_subdub_dub_audio_policy"],
    ).resolve_subdub_dub_audio_policy(
        {"target_language": "English", "translate_requested": "1"},
        {"source_segments": source, "output_segments": translated["segments"]},
    )
    assert [item["text"] for item in policy["tts_segments"]] == ["Hello"]
    assert policy["source_tts_rendered"] is False


def test_ass_bottom_renderer_preserves_exact_overlapping_source_timestamps(monkeypatch):
    style = {
        "show_subtitles": True,
        "subtitle_font_resolution_ok": True,
        "font": "Noto Sans",
        "size": 42,
        "render_size": 42,
        "outline": 2,
        "shadow": 1,
        "position": "bottom",
        "align": "center",
        "play_res_x": 1280,
        "play_res_y": 720,
        "max_lines": 2,
        "m4live1_style_renderer_only": True,
        "m4live2_subtitle_bottom_lock": True,
    }
    monkeypatch.setattr(bot, "subdub_normalize_style", lambda _value=None: dict(style))

    ass = bot.subdub_generate_ass_from_srt(SOURCE_SRT, style)

    assert "Dialogue: 0,0:00:00.00,0:00:02.00" in ass
    assert "Dialogue: 0,0:00:01.50,0:00:03.00" in ass
    assert "subtitle_cue_timestamps_mutated: no" in ass


def test_long_chunk_plan_has_no_one_second_tail_and_covers_full_input():
    for duration, expected_count in ((31, 2), (60, 2), (61, 3), (299, 10)):
        plan = bot.subdub_long_video_chunk_plan(duration)
        ranges = plan["chunk_ranges"]
        assert len(ranges) == expected_count
        assert ranges[0]["start"] == 0
        assert ranges[-1]["end"] == duration
        assert all(item["end"] > item["start"] for item in ranges)
        assert min(item["end"] - item["start"] for item in ranges) >= 10


def test_unicode_ass_basic_fallback_keeps_resolved_ass_font():
    source = inspect.getsource(bot.video_dubbing_render_video)
    assert "basic_filter = subtitle_filter or fallback_subtitle_filter" in source
    assert "basic_filter = fallback_subtitle_filter if advanced_filters" not in source
