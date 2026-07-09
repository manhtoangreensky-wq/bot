import asyncio

import bot


def _source_segments(count=10):
    segments = []
    current = 0.0
    for index in range(1, count + 1):
        duration = 1.1 + (index % 3) * 0.37
        segments.append({
            "index": index,
            "start": round(current, 3),
            "end": round(current + duration, 3),
            "text": f"source cue {index}",
        })
        current += duration + 0.23
    return segments


def _assert_same_timeline(source, output):
    assert len(output) == len(source)
    for src, dst in zip(source, output):
        assert dst["index"] == src["index"]
        assert dst["start"] == src["start"]
        assert dst["end"] == src["end"]


def test_timing1_translation_same_count_preserves_all_cue_times():
    source = _source_segments(10)
    translated = [
        {"index": item["index"], "start": 99, "end": 100, "text": f"translated {item['index']}"}
        for item in source
    ]

    output = bot.subdub_retime_translated_segments_to_source(source, translated)

    _assert_same_timeline(source, output)
    assert [item["text"] for item in output] == [f"translated {idx}" for idx in range(1, 11)]


def test_timing1_long_translation_wraps_inside_same_cue_only():
    source = _source_segments(2)
    translated = [
        {"index": 1, "start": 0, "end": 99, "text": " ".join(["translated"] * 30)},
        {"index": 2, "start": 0, "end": 99, "text": "short text"},
    ]

    retimed = bot.subdub_retime_translated_segments_to_source(source, translated)
    output = bot.video_dubbing_qc_segments(retimed, preserve_timestamps=True)

    _assert_same_timeline(source, output)
    assert all(len(str(item["text"]).splitlines()) <= 2 for item in output)


def test_timing1_missing_translation_does_not_shift_later_cues():
    source = _source_segments(5)
    translated = [
        {"index": 1, "start": 0, "end": 99, "text": "translated one"},
        {"index": 3, "start": 0, "end": 99, "text": "translated three"},
        {"index": 5, "start": 0, "end": 99, "text": "translated five"},
    ]

    output = bot.subdub_retime_translated_segments_to_source(source, translated)

    _assert_same_timeline(source, output)
    assert output[1]["text"] == source[1]["text"]
    assert output[1]["translate_missing"] is True
    assert output[2]["text"] == "translated three"


def test_timing1_extra_translation_does_not_add_new_cue():
    source = _source_segments(3)
    translated = [
        {"index": 1, "start": 0, "end": 99, "text": "one"},
        {"index": 2, "start": 0, "end": 99, "text": "two"},
        {"index": 3, "start": 0, "end": 99, "text": "three"},
        {"index": 4, "start": 0, "end": 99, "text": "extra should be ignored"},
    ]

    output = bot.subdub_retime_translated_segments_to_source(source, translated)

    _assert_same_timeline(source, output)
    assert [item["text"] for item in output] == ["one", "two", "three"]


def test_timing1_translate_subtitle_segments_preserves_source_timeline(monkeypatch):
    source = _source_segments(4)

    async def fake_translate(text, target_language, **kwargs):
        if text.endswith("2"):
            return {"text": "", "provider": "fixture"}
        return {"text": f"{target_language}: {text}", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)

    result = asyncio.run(bot.translate_subtitle_segments(source, "English", allow_admin=True, updated_by="pytest"))

    _assert_same_timeline(source, result["segments"])
    assert result["segments"][1]["text"] == source[1]["text"]
    assert len(bot.video_dubbing_segments_from_subtitle(result["srt"])) == len(source)


def test_timing1_subtitle_plus_dub_uses_same_translated_cue_timeline(monkeypatch):
    source = _source_segments(3)

    async def fake_translate(text, target_language, **kwargs):
        return {"text": f"{target_language}: {text}", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)

    result = asyncio.run(bot.translate_subtitle_segments(source, "Japanese", allow_admin=True, updated_by="pytest"))

    _assert_same_timeline(source, result["segments"])
    assert "Japanese: source cue 1" in result["srt"]
