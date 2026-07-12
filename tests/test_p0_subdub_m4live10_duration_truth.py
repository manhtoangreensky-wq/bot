import asyncio
import subprocess
from pathlib import Path

import pytest

import bot
from services import subdub_long_media, subtitle_dub_product_pipeline


def _ffmpeg_path() -> str:
    path = bot.frame_video_ffmpeg_path()
    if not path:
        pytest.skip("ffmpeg is required for the offline duration fixture")
    return path


def _make_video(path: Path, duration: int) -> bytes:
    subprocess.run(
        [
            _ffmpeg_path(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=160x90:r=5:d={duration}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


def _make_tts_audio(path: Path, duration: float = 2.0) -> bytes:
    subprocess.run(
        [
            _ffmpeg_path(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=24000:duration={duration}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


@pytest.fixture(scope="module")
def synthetic_tts(tmp_path_factory):
    root = tmp_path_factory.mktemp("m4live10_tts")
    return _make_tts_audio(root / "tts.mp3")


@pytest.mark.parametrize("duration", [30, 31, 60])
def test_short_tts_never_truncates_source_video(tmp_path, synthetic_tts, duration):
    source = _make_video(tmp_path / f"source_{duration}.mp4", duration)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            source,
            dubbed_audio=synthetic_tts,
            original_audio_mode="mute",
            require_audio=True,
        )
    )
    validation = asyncio.run(
        bot.subdub_validate_video_output(
            output,
            require_audio=True,
            expected_duration=duration,
        )
    )

    assert validation["ok"] is True
    assert validation["actual_duration"] >= duration * 0.97
    assert validation["actual_duration"] <= duration + 1.0
    assert validation["duration_coverage_ok"] is True
    assert "shortest_used=no" in detail


def test_combo_30s_keeps_source_duration_and_cue_locked_subtitle(tmp_path, synthetic_tts):
    source = _make_video(tmp_path / "combo_source.mp4", 30)
    subtitle = (
        "1\n00:00:01,000 --> 00:00:03,000\nTranslated one\n\n"
        "2\n00:00:20,000 --> 00:00:24,000\nTranslated two\n"
    ).encode("utf-8")

    output, _detail = asyncio.run(
        bot.video_dubbing_render_video(
            source,
            dubbed_audio=synthetic_tts,
            subtitle_bytes=subtitle,
            original_audio_mode="mute",
            require_audio=True,
        )
    )
    validation = asyncio.run(
        bot.subdub_validate_video_output(output, require_audio=True, expected_duration=30)
    )

    assert validation["ok"] is True
    assert validation["actual_duration"] >= 29.1


def test_message_id_cannot_turn_two_second_video_into_30s_success(tmp_path, monkeypatch):
    short_video = _make_video(tmp_path / "short.mp4", 2)
    calls = []

    async def fake_delivery(*_args, **_kwargs):
        calls.append(1)
        return {"sent": True, "delivery_method": "video", "telegram_message_id": "should-not-send"}

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_delivery)
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            object(),
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            video_bytes=short_video,
            strict_validation=True,
            expected_duration_seconds=30,
        )
    )

    assert calls == []
    assert result["final_mp4_delivered"] is False
    assert result["duration_coverage_ok"] is False
    assert result["success_blocked_reason"] == "video_duration_coverage_failed"
    assert bot.subdub_result_has_delivered_video({**result, "telegram_message_id": "fixture"}) is False


def test_canonical_path_wins_over_short_preview(tmp_path, monkeypatch):
    final_path = tmp_path / "final.mp4"
    final_bytes = _make_video(final_path, 4)
    preview_bytes = _make_video(tmp_path / "preview.mp4", 1)
    delivered = []

    async def fake_delivery(_message, payload, **_kwargs):
        delivered.append(bytes(payload))
        return {
            "sent": True,
            "delivery_method": "video",
            "telegram_message_id": "canonical-message",
            "file_size_mb": 0.1,
            "size_limit_used": 45.0,
        }

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_delivery)
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            object(),
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            video_bytes=preview_bytes,
            canonical_video_path=str(final_path),
            strict_validation=True,
            expected_duration_seconds=4,
        )
    )

    assert delivered == [final_bytes]
    assert result["final_mp4_delivered"] is True
    assert result["canonical_final_artifact_source"] == "workspace_final_mp4"


def test_translated_long_text_stays_one_cue_with_exact_source_timestamps(monkeypatch):
    source = [
        {"index": 7, "start": 4.125, "end": 8.875, "text": "source cue"},
    ]
    translated_text = "This translated sentence is deliberately long and must wrap inside one cue without creating a second timeline event"

    async def fake_translate(*_args, **_kwargs):
        return {"text": translated_text, "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    result = asyncio.run(bot.translate_subtitle_segments(source, "English"))
    cue = result["segments"][0]

    assert len(result["segments"]) == 1
    assert cue["index"] == 7
    assert (cue["start"], cue["end"]) == (4.125, 8.875)
    assert cue["text"].replace("\n", " ") == translated_text
    assert cue["text"].count("\n") <= 1
    assert result["cue_start_mismatch_count"] == 0
    assert result["cue_end_mismatch_count"] == 0


@pytest.mark.parametrize("mode", ["dub", "subtitle_plus_dub"])
def test_complete_tts_segment_coverage_is_persisted(mode):
    segments = [
        {"index": 1, "start": 0.0, "end": 1.0, "text": "one"},
        {"index": 2, "start": 2.0, "end": 3.0, "text": "two"},
        {"index": 3, "start": 4.0, "end": 5.0, "text": "three"},
    ]

    async def prepare(state):
        return {
            "state": dict(state),
            "source_bytes": b"source",
            "content_type": "video/mp4",
            "source_segments": segments,
            "output_segments": segments,
            "source_subtitle": bot.video_dubbing_srt_from_segments(segments),
            "output_subtitle": bot.video_dubbing_srt_from_segments(segments),
            "source_script": "one two three",
            "output_script": "one two three",
        }

    async def synthesize(items, **_kwargs):
        return {
            "provider": "fixture",
            "chunks": [
                {**item, "audio_bytes": f"audio-{item['index']}".encode(), "audio_duration": 0.5}
                for item in items
            ],
        }

    async def timeline(chunks, duration):
        assert len(chunks) == 3
        assert duration == 6
        return b"timeline", "fixture"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=mode,
            state={"video_duration": 6, "target_language": "English"},
            user_id=1,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "fixture-voice",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=lambda audio: (audio, "fixture"),
            render_video=lambda *_args, **_kwargs: (b"mp4", "fixture"),
            video_render_ready=lambda _value: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["tts_expected_segments"] == 3
    assert result["tts_generated_segments"] == 3
    assert result["tts_mixed_segments"] == 3
    assert result["tts_dropped_segments"] == 0
    assert result["tts_timeline_duration"] == 6


def test_receipt_uses_actual_ffprobe_duration_not_requested_duration():
    result = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "terminal_state": "delivered",
        "video_delivery_message_id": "telegram-message",
        "duration_coverage_ok": True,
        "expected_duration": 30,
        "canonical_final_artifact_duration": 29.8,
        "final_mp4_delivered": True,
    }
    text = bot.video_dubbing_receipt_text({"video_duration": 300}, result, "vi")

    assert "29 giay" not in text.lower()
    assert "29 giây" in text
    assert "5 phút" not in text


def test_long_project_plans_301_and_601_seconds_in_order():
    plan_301 = bot.subdub_long_project_plan(301)
    plan_601 = bot.subdub_long_project_plan(601)

    assert plan_301["project_part_ranges"] == [
        {"index": 1, "start": 0, "end": 300, "duration": 300},
        {"index": 2, "start": 300, "end": 301, "duration": 1},
    ]
    assert plan_601["project_part_ranges"] == [
        {"index": 1, "start": 0, "end": 300, "duration": 300},
        {"index": 2, "start": 300, "end": 600, "duration": 300},
        {"index": 3, "start": 600, "end": 601, "duration": 1},
    ]


def test_boundary_cues_have_no_negative_or_missing_local_timestamps():
    source = [
        {"index": 1, "start": 299.5, "end": 301.0, "text": "crossing"},
        {"index": 2, "start": 300.0, "end": 301.5, "text": "exact boundary"},
    ]
    first = subdub_long_media.slice_segments_for_project_part(source, part_start=0, part_end=300)
    second = subdub_long_media.slice_segments_for_project_part(source, part_start=300, part_end=601)

    assert first == [{"index": 1, "start": 299.5, "end": 300.0, "text": "crossing"}]
    assert second == [
        {"index": 1, "start": 0.0, "end": 1.0, "text": "crossing"},
        {"index": 2, "start": 0.0, "end": 1.5, "text": "exact boundary"},
    ]
    assert all(item["start"] >= 0 and item["end"] > item["start"] for item in first + second)


def test_duration_debug_and_terminal_gate_fields_are_publicly_auditable():
    text = bot.subtitle_dub_debug_text(
        {
            "job_id": "M4LIVE10",
            "source_duration": 30,
            "final_mp4_duration": 30,
            "duration_coverage_ratio": 1.0,
            "canonical_final_artifact_path": "masked/final.mp4",
            "canonical_final_artifact_source": "workspace_final_mp4",
            "tts_expected_segments": 3,
            "tts_generated_segments": 3,
            "tts_mixed_segments": 3,
            "tts_dropped_segments": 0,
            "cue_start_mismatch_count": 0,
            "cue_end_mismatch_count": 0,
            "chunk_count": 1,
            "video_delivery_message_id": "123",
        }
    ).lower()

    for token in ("source duration", "final mp4 duration", "coverage", "tts expected", "cue start mismatch"):
        assert token in text
