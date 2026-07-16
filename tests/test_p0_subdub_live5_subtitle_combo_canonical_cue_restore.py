import asyncio
import inspect
import re
import subprocess
from pathlib import Path

import pytest

import bot
from services import subdub_canonical_cues as canonical


REPO = Path(__file__).resolve().parents[1]


def _source_cues():
    return [
        {"index": 1, "start": 0.5, "end": 2.25, "text": "第一句"},
        {"index": 2, "start": 3.0, "end": 5.75, "text": "第二句"},
        {"index": 3, "start": 7.2, "end": 9.4, "text": "第三句"},
    ]


def _top_level_function_source(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(rf"^(?:async\s+)?def\s+{re.escape(name)}\s*\(", line)
    )
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^(?:async\s+def|def|class)\s+", lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip()


def test_live5_canonical_cue_contract_preserves_truth_fields():
    cues = canonical.canonicalize_segments(
        _source_cues(),
        extraction_source="burned_in_ocr",
        source_language="zh",
    )

    assert len(cues) == 3
    assert [cue["source_index"] for cue in cues] == [1, 2, 3]
    assert [(cue["source_start_ms"], cue["source_end_ms"]) for cue in cues] == [
        (500, 2250),
        (3000, 5750),
        (7200, 9400),
    ]
    assert all(cue["cue_id"].startswith("cue-") for cue in cues)
    assert all(cue["extraction_source"] == "burned_in_ocr" for cue in cues)
    assert all(cue["version"] == canonical.CANONICAL_CUE_VERSION for cue in cues)


def test_live5_burned_in_ocr_groups_frames_into_real_cues():
    observations = [
        {"frame_index": 1, "timestamp_ms": 0, "text": "第一句", "confidence": 0.91},
        {"frame_index": 2, "timestamp_ms": 500, "text": "第一句", "confidence": 0.93},
        {"frame_index": 3, "timestamp_ms": 1000, "text": "第一句", "confidence": 0.92},
        {"frame_index": 4, "timestamp_ms": 2000, "text": "第二句", "confidence": 0.88},
        {"frame_index": 5, "timestamp_ms": 2500, "text": "第二句", "confidence": 0.90},
    ]

    cues = canonical.group_ocr_observations(
        observations,
        frame_interval_ms=500,
        duration_ms=4000,
        source_language="zh",
    )

    assert [cue["source_text"] for cue in cues] == ["第一句", "第二句"]
    assert [(cue["source_start_ms"], cue["source_end_ms"]) for cue in cues] == [
        (0, 1500),
        (2000, 3000),
    ]


def test_live5_embedded_subtitle_has_priority_and_skips_ocr_asr(monkeypatch):
    calls = {"ocr": 0, "asr": 0}

    async def embedded(*_args, **_kwargs):
        return "1\n00:00:00,500 --> 00:00:02,000\nembedded line\n", "embedded_subtitle"

    async def ocr(*_args, **_kwargs):
        calls["ocr"] += 1
        return {"segments": []}

    async def asr(*_args, **_kwargs):
        calls["asr"] += 1
        return {"output_valid": False}

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_burned_in_subtitle_cues", ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(bot.video_dubbing_resolve_canonical_source_script(b"video", "video/mp4", None, duration_seconds=28))

    assert result["extraction_source"] == "embedded_subtitle"
    assert len(result["canonical_cues"]) == 1
    assert calls == {"ocr": 0, "asr": 0}


def test_live5_burned_in_ocr_has_priority_over_asr(monkeypatch):
    calls = {"asr": 0}

    async def embedded(*_args, **_kwargs):
        return "", "none"

    async def ocr(*_args, **_kwargs):
        return {
            "segments": canonical.canonicalize_segments(
                _source_cues(), extraction_source="burned_in_ocr", source_language="zh"
            ),
            "subtitle": "",
            "detail": "fixture",
            "language_spec": "chi_sim+eng",
            "duration_seconds": 28,
        }

    async def asr(*_args, **_kwargs):
        calls["asr"] += 1
        return {"output_valid": False}

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_burned_in_subtitle_cues", ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(bot.video_dubbing_resolve_canonical_source_script(b"video", "video/mp4", None, duration_seconds=28))

    assert result["extraction_source"] == "burned_in_ocr"
    assert len(result["canonical_cues"]) == 3
    assert calls["asr"] == 0


def test_live5_ocr_never_falls_back_to_english_for_unknown_or_cjk_source():
    assert bot.subdub_tesseract_language_spec("auto", {"eng"}) == ""
    assert bot.subdub_tesseract_language_spec("zh", {"eng"}) == ""
    assert bot.subdub_tesseract_language_spec("zh", {"chi_sim", "eng"}) == "chi_sim+eng"
    assert bot.subdub_tesseract_language_spec("en", {"eng"}) == "eng"


def test_live5_ocr_rejects_wrong_script_before_it_becomes_canonical_source():
    wrong_script = canonical.canonicalize_segments(
        [{"index": 1, "start": 0.0, "end": 1.0, "text": "FEMB PIE TBRYRAEELH"}],
        extraction_source="burned_in_ocr",
        source_language="zh",
    )
    correct_script = canonical.canonicalize_segments(
        [{"index": 1, "start": 0.0, "end": 1.0, "text": "这是字幕"}],
        extraction_source="burned_in_ocr",
        source_language="zh",
    )

    assert bot.subdub_ocr_cues_match_source_language(wrong_script, "zh", "chi_sim+eng") is False
    assert bot.subdub_ocr_cues_match_source_language(correct_script, "zh", "chi_sim+eng") is True


def test_live5_ocr_unavailable_uses_timestamp_preserving_asr_fallback(monkeypatch):
    captured = {}

    async def embedded(*_args, **_kwargs):
        return "", "none"

    async def ocr(*_args, **_kwargs):
        return {"segments": [], "detail": "burned_in_ocr_missing_tesseract"}

    async def asr(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "output_valid": True,
            "segments": _source_cues(),
            "detected_language": "zh",
            "provider": "fixture_asr",
            "detail": "fixture",
            "duration_seconds": 28,
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_burned_in_subtitle_cues", ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    result = asyncio.run(bot.video_dubbing_resolve_canonical_source_script(b"video", "video/mp4", None, duration_seconds=28))

    assert result["extraction_source"] == "asr_fallback"
    assert captured["preserve_timestamps"] is True
    assert canonical.timeline_signature(result["canonical_cues"]) == canonical.timeline_signature(
        canonical.canonicalize_segments(_source_cues(), extraction_source="asr_fallback")
    )


def test_live5_no_cue_fails_cleanly_instead_of_fake_success(monkeypatch):
    async def embedded(*_args, **_kwargs):
        return "", "none"

    async def ocr(*_args, **_kwargs):
        return {"segments": [], "detail": "no_text"}

    async def asr(*_args, **_kwargs):
        return {"output_valid": False, "status": "asr_no_speech"}

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", embedded)
    monkeypatch.setattr(bot, "video_dubbing_extract_burned_in_subtitle_cues", ocr)
    monkeypatch.setattr(bot, "transcribe_media_to_segments", asr)

    with pytest.raises(RuntimeError, match="asr_no_speech"):
        asyncio.run(bot.video_dubbing_resolve_canonical_source_script(b"video", "video/mp4", None, duration_seconds=28))


def test_live5_translation_changes_text_only_and_wraps_inside_same_cue(monkeypatch):
    source = canonical.canonicalize_segments(_source_cues(), extraction_source="burned_in_ocr", source_language="zh")

    async def translate(text, target_language, **_kwargs):
        return {"text": f"{target_language} " + "translated words " * 12 + text, "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", translate)
    result = asyncio.run(bot.translate_canonical_subtitle_segments(source, "vi"))

    assert canonical.same_timeline(source, result["segments"])
    assert len(result["segments"]) == len(source)
    assert all(len(cue["text"].splitlines()) <= 2 for cue in result["segments"])


def test_live5_combo_tts_uses_one_segment_per_canonical_cue(monkeypatch):
    translated = canonical.apply_translations(
        canonical.canonicalize_segments(_source_cues(), extraction_source="burned_in_ocr"),
        [
            {"source_index": 1, "text": "cau mot"},
            {"source_index": 2, "text": "cau hai"},
            {"source_index": 3, "text": "cau ba"},
        ],
        target_language="vi",
    )
    spoken = []

    async def tts(text, *_args, **_kwargs):
        spoken.append(text)
        return "fixture_tts", b"audio", "ok"

    async def duration(_audio):
        return 0.8

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", duration)
    result = asyncio.run(bot.synthesize_canonical_dub_segment_chunks(translated, voice_id="female-fixture"))

    assert len(result["chunks"]) == len(translated) == 3
    assert spoken == [cue["translated_text"] for cue in translated]
    assert [chunk["cue_id"] for chunk in result["chunks"]] == [cue["cue_id"] for cue in translated]
    assert result["canonical_timeline_signature"] == canonical.timeline_signature(translated)


def test_live5_combo_audio_is_fitted_per_cue_without_global_drift(monkeypatch):
    commands = []

    async def fake_ffmpeg(command, timeout=0):
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"timeline-audio")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_ffmpeg)
    chunks = [
        {"start": 0.5, "end": 2.25, "audio_duration": 1.9, "audio_bytes": b"a"},
        {"start": 3.0, "end": 5.75, "audio_duration": 1.0, "audio_bytes": b"b"},
    ]

    audio, detail = asyncio.run(bot.build_canonical_dub_timeline_audio(chunks, total_duration=26.0))

    command = commands[-1]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert audio == b"timeline-audio"
    assert "adelay=500|500" in filter_graph
    assert "adelay=3000|3000" in filter_graph
    assert "atrim=duration=26.000" in filter_graph
    assert "-shortest" not in command
    assert "duration=26.000" in detail


@pytest.mark.parametrize("duration", [26.0, 28.0, 30.0, 31.0, 60.0])
def test_live5_duration_truth_accepts_full_length_fixtures(duration):
    assert canonical.duration_matches_source(duration, duration - 0.2)["ok"] is True
    assert canonical.duration_matches_source(duration, 2.0)["ok"] is False


def test_live5_renderer_preserves_source_duration_and_does_not_use_shortest(monkeypatch):
    commands = []

    async def probe(_payload):
        return {"duration": 26.0, "has_audio": True, "width": 720, "height": 1280}

    async def fake_ffmpeg(command, timeout=0):
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"mp4")
        return True, "ok"

    async def validate(_payload, require_audio=False):
        return {"ok": True, "duration": 26.0, "has_audio": bool(require_audio), "detail": "fixture"}

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", probe)
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_ffmpeg)
    monkeypatch.setattr(bot, "subdub_validate_video_output", validate)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"source",
            dubbed_audio=b"dub",
            subtitle_style={"show_subtitles": False},
            preserve_source_duration=True,
            require_audio=True,
        )
    )

    assert output == b"mp4"
    assert "source_duration_preserved=26.000" in detail
    assert "-shortest" not in commands[-1]
    assert commands[-1][commands[-1].index("-t") + 1] == "26.000"


def test_live8_all_four_lanes_use_one_canonical_cue_contract_and_keep_provider_core():
    assert bot.subdub_mode_uses_canonical_cues(bot.VIDEO_SUBTITLE_MODE_CREATE) is True
    assert bot.subdub_mode_uses_canonical_cues(bot.VIDEO_SUBTITLE_MODE_TRANSLATE) is True
    assert bot.subdub_mode_uses_canonical_cues(bot.VIDEO_SUBTITLE_MODE_DUB) is True
    assert bot.subdub_mode_uses_canonical_cues(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB) is True

    baseline = subprocess.run(
        ["git", "show", "origin/main:bot.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    current = (REPO / "bot.py").read_text(encoding="utf-8")
    locked_functions = (
        "resolve_video_dub_tts_voice",
        "resolve_video_dub_tts_voice_id",
        "video_dubbing_resolve_source_script",
        "send_public_subtitle_dub_final_outputs",
    )
    for name in locked_functions:
        assert _top_level_function_source(current, name) == _top_level_function_source(baseline, name), name


def test_live5_final_video_and_telegram_message_are_required_before_success():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "if final_video_required and not video_output:" in source
    assert "partial_result and (audio_bytes or srt_bytes or subtitle_items)" not in source
    assert "FINAL_VIDEO_DELIVERY_NOT_CONFIRMED" in source
    assert "delivered_video_message_id" in source
    # The core may only return Telegram delivery evidence. One shared outer
    # terminal function owns the 100% panel and exactly-once receipt.
    assert "await _progress(\"delivered\")" not in source
    assert "delivery_confirmed" in source
    assert "mark_subtitle_dub_pipeline_output_sent" in source
