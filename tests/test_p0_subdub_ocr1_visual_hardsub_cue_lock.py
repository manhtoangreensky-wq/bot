import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot
from services import subdub_visual_subtitle


def test_visual_observations_become_non_overlapping_source_timed_cues():
    observations = [
        {"timestamp": 0.0, "text": ""},
        {"timestamp": 0.5, "text": "你好，世界"},
        {"timestamp": 1.0, "text": "你好, 世界"},
        {"timestamp": 1.5, "text": ""},
        {"timestamp": 2.0, "text": "再见"},
        {"timestamp": 2.5, "text": "再见"},
        {"timestamp": 3.0, "text": ""},
    ]

    cues = subdub_visual_subtitle.observations_to_cues(
        observations,
        frame_interval=0.5,
        source_duration=4.0,
    )

    assert [(item["start"], item["end"]) for item in cues] == [(0.5, 1.5), (2.0, 3.0)]
    assert [item["index"] for item in cues] == [1, 2]
    assert all(item["timing_source"] == "visual_hardsub_ocr" for item in cues)
    assert all(cues[index]["end"] <= cues[index + 1]["start"] for index in range(len(cues) - 1))


def test_visual_blackbox_uses_frame_timestamps_without_audio_or_provider_calls():
    frame_paths = [f"frame-{index}.png" for index in range(6)]
    texts = ["", "Line one", "Line one", "", "Line two", "Line two"]
    calls = []

    async def extract_frames(source_bytes, fps, max_frames):
        assert source_bytes == b"video"
        assert fps == 2.0
        assert max_frames == 20
        return frame_paths

    async def ocr_frame(path, language):
        calls.append((path, language))
        return {"text": texts[frame_paths.index(path)], "language": "eng"}

    result = asyncio.run(
        subdub_visual_subtitle.extract_visual_subtitle_cues(
            b"video",
            source_duration=3.0,
            source_language="en",
            frames_per_second=2.0,
            max_frames=20,
            extract_frames=extract_frames,
            ocr_frame=ocr_frame,
        )
    )

    assert result["ok"] is True
    assert result["subtitle_timing_source"] == "visual_hardsub_ocr"
    assert [(item["start"], item["end"]) for item in result["segments"]] == [(0.5, 1.5), (2.0, 3.0)]
    assert len(calls) == len(frame_paths)


def test_embedded_subtitle_stays_first_priority(monkeypatch):
    embedded = "1\n00:00:01,000 --> 00:00:02,000\nEmbedded\n"

    async def embedded_subtitle(*_args, **_kwargs):
        return embedded, "embedded_subtitle"

    async def visual_subtitle(*_args, **_kwargs):
        raise AssertionError("visual OCR must not replace an embedded subtitle stream")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded_subtitle)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", visual_subtitle)
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            prefer_visual_subtitles=True,
        )
    )

    assert result["source_kind"] == "embedded_subtitle"
    assert result["subtitle"] == embedded


def test_visual_hardsub_is_used_before_asr_when_requested(monkeypatch):
    segments = [{"index": 1, "start": 1.0, "end": 2.5, "text": "字幕"}]

    async def no_embedded(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def visual_subtitle(*_args, **_kwargs):
        return {
            "ok": True,
            "subtitle": bot.video_dubbing_srt_from_segments(segments),
            "script": "字幕",
            "segments": segments,
            "detail": "frames=6; cues=1",
            "frame_count": 6,
            "cue_count": 1,
            "subtitle_timing_source": "visual_hardsub_ocr",
        }

    async def asr_must_not_run(*_args, **_kwargs):
        raise AssertionError("ASR must not overwrite visual subtitle cues")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", visual_subtitle)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr_must_not_run)
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            duration_seconds=3,
            source_language="zh",
            prefer_visual_subtitles=True,
        )
    )

    assert result["source_kind"] == "visual_hardsub_ocr"
    assert result["segments"] == segments
    assert result["subtitle_timing_source"] == "visual_hardsub_ocr"
    assert result["visual_ocr_frame_count"] == 6


def test_visual_unavailable_falls_back_to_existing_asr_lane(monkeypatch):
    async def no_embedded(*_args, **_kwargs):
        return "", "no_embedded_subtitle"

    async def no_visual(*_args, **_kwargs):
        return {"ok": False, "status": "visual_ocr_runtime_missing", "segments": []}

    async def asr_result(*_args, **_kwargs):
        return {
            "output_valid": True,
            "transcript_text": "spoken text",
            "segments": [{"index": 1, "start": 0.25, "end": 1.75, "text": "spoken text"}],
            "provider": "fixture",
            "detected_language": "en",
            "duration_seconds": 2,
            "subtitle_timing_source": "provider_segments",
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", no_embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_visual_subtitle", no_visual)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr_result)
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"video",
            "video/mp4",
            SimpleNamespace(),
            duration_seconds=2,
            prefer_visual_subtitles=True,
        )
    )

    assert result["source_kind"] == "asr"
    assert result["segments"][0]["start"] == 0.25


def test_visual_cues_remain_locked_after_translation(monkeypatch):
    source = [
        {"index": 1, "start": 0.5, "end": 1.5, "text": "第一行"},
        {"index": 2, "start": 2.0, "end": 3.25, "text": "第二行"},
    ]
    translated_texts = iter(["Dong mot", "Dong hai"])

    async def translate(*_args, **_kwargs):
        return {"text": next(translated_texts), "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", translate)
    result = asyncio.run(bot.translate_subtitle_segments(source, "vi"))

    assert [(item["start"], item["end"]) for item in result["segments"]] == [(0.5, 1.5), (2.0, 3.25)]
    assert result["cue_start_mismatch_count"] == 0
    assert result["cue_end_mismatch_count"] == 0


def test_tesseract_language_mapping_covers_translation_catalog(monkeypatch):
    available = set(bot.SUBDUB_TESSERACT_LANGUAGE_MAP.values()) | {"eng"}
    monkeypatch.setattr(bot, "subdub_tesseract_available_languages", lambda: available)

    for language_code, expected_pack in bot.SUBDUB_TESSERACT_LANGUAGE_MAP.items():
        selected, reason = bot.subdub_tesseract_language_pack(language_code)
        assert selected == expected_pack
        assert reason == "source_language"


def test_runtime_installs_local_multilingual_tesseract():
    dockerfile = (Path(bot.__file__).resolve().parent / "Dockerfile").read_text(encoding="utf-8")
    assert "tesseract-ocr" in dockerfile
    assert "tesseract-ocr-all" in dockerfile


def test_visual_ocr_does_not_enter_renderer_or_delivery_lanes():
    renderer_source = inspect.getsource(bot.video_dubbing_render_video)
    delivery_source = inspect.getsource(bot.send_public_subtitle_dub_final_outputs)

    assert "visual_ocr" not in renderer_source
    assert "visual_ocr" not in delivery_source
