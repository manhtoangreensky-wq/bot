import asyncio
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
from services import dubbing_pipeline, subtitle_dub_product_pipeline


def test_tts_segment_with_nonempty_bytes_but_zero_duration_is_rejected(monkeypatch):
    async def fake_tts(*_args, **_kwargs):
        return "key4u_minimax", b"not-audio-data", "http=200"

    async def zero_duration(*_args, **_kwargs):
        return 0.0

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", zero_duration)

    with pytest.raises(RuntimeError, match=r"tts_segment_invalid:1:audio_duration_unavailable"):
        asyncio.run(
            bot.synthesize_dub_segment_chunks(
                [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}],
                voice_id="Vietnamese_female_4_v1",
                allow_admin=True,
            )
        )


def test_tts_audio_qc_rejects_click_only_activity(monkeypatch):
    async def duration(*_args, **_kwargs):
        return 2.0

    async def activity(*_args, **_kwargs):
        return {
            "ok": True,
            "detail": "decoded",
            "duration": 2.0,
            "non_silent_seconds": 0.02,
            "active_ratio": 0.01,
        }

    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", duration)
    monkeypatch.setattr(bot, "subdub_audio_activity_metrics", activity)

    qc = asyncio.run(bot.subdub_validate_tts_audio_bytes(b"x" * 4096))

    assert qc["ok"] is False
    assert qc["detail"] == "speech_activity_missing"
    assert qc["audio_bytes"] == 4096


def test_timeline_qc_accepts_sparse_but_real_speech_after_each_cue_passes(monkeypatch):
    async def duration(*_args, **_kwargs):
        return 100.0

    async def activity(*_args, **_kwargs):
        return {
            "ok": True,
            "detail": "decoded",
            "duration": 100.0,
            "non_silent_seconds": 0.2,
            "active_ratio": 0.002,
        }

    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", duration)
    monkeypatch.setattr(bot, "subdub_audio_activity_metrics", activity)

    strict = asyncio.run(bot.subdub_validate_tts_audio_bytes(b"x" * 4096))
    timeline = asyncio.run(bot.subdub_validate_tts_timeline_audio_bytes(b"x" * 4096))

    assert strict["ok"] is False
    assert timeline["ok"] is True
    assert timeline["detail"] == "speech_activity_ok"


@pytest.mark.parametrize(
    ("lavfi_source", "expected_ok", "expected_detail"),
    [
        ("sine=frequency=440:sample_rate=32000", True, "speech_activity_ok"),
        ("anullsrc=r=32000:cl=mono", False, "speech_activity_missing"),
    ],
)
def test_tts_audio_qc_uses_real_ffmpeg_activity_fixture(
    tmp_path,
    lavfi_source,
    expected_ok,
    expected_detail,
):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    output = tmp_path / "fixture.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            lavfi_source,
            "-t",
            "1.0",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output),
        ],
        check=True,
        capture_output=True,
    )

    qc = asyncio.run(bot.subdub_validate_tts_audio_bytes(output.read_bytes()))

    assert qc["ok"] is expected_ok
    assert qc["detail"] == expected_detail
    assert qc["duration"] >= 0.9


def test_dub_timeline_plan_waits_for_previous_sentence_without_overlap():
    plan = bot.subdub_plan_dub_timeline(
        [
            {"cue_id": "cue-1", "start": 0.0, "end": 2.0, "audio_duration": 2.2},
            {"cue_id": "cue-2", "start": 2.0, "end": 4.0, "audio_duration": 2.1},
        ],
        5.0,
    )

    assert plan["ok"] is True
    assert plan["tempo_ratio"] == 1.0
    assert plan["overlap_count"] == 0
    assert plan["scheduled"][0]["scheduled_end"] == pytest.approx(2.2)
    assert plan["scheduled"][1]["scheduled_start"] == pytest.approx(2.2)
    assert plan["scheduled"][1]["scheduled_end"] == pytest.approx(4.3)


def test_dub_timeline_refuses_to_extend_past_the_one_hour_output_limit():
    plan = bot.subdub_plan_dub_timeline(
        [
            {
                "cue_id": "last-cue",
                "start": 3590.0,
                "end": 3600.0,
                "audio_duration": 20.0,
            }
        ],
        3600.0,
        max_output_duration=3600.0,
    )

    assert plan["ok"] is False
    assert plan["scheduled"] == []
    assert plan["blocker"].startswith("tts_timeline_exceeds_output_limit:")
    assert "max_output_duration=3600.000" in plan["blocker"]


def test_dub_timeline_uses_sequential_concat_and_boundary_fades(monkeypatch):
    commands = []

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"valid-sequential-audio")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    chunks = [
        {"cue_id": "cue-1", "start": 0.0, "end": 2.0, "audio_duration": 2.2, "audio_bytes": b"one"},
        {"cue_id": "cue-2", "start": 2.0, "end": 4.0, "audio_duration": 2.1, "audio_bytes": b"two"},
    ]

    output, detail = asyncio.run(bot.build_dub_timeline_audio(chunks, 5.0))

    assert output == b"valid-sequential-audio"
    assert "sequential=yes" in detail
    assert "overlap_count=0" in detail
    filter_graph = commands[-1][commands[-1].index("-filter_complex") + 1]
    assert "concat=" in filter_graph
    assert "afade=t=in" in filter_graph
    assert "afade=t=out" in filter_graph
    assert "amix=inputs=2" not in filter_graph


def test_dub_timeline_real_ffmpeg_fixture_is_decodable_and_source_bounded(tmp_path):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")

    chunks = []
    for index, (start, frequency) in enumerate(((0.25, 440), (1.1, 660)), start=1):
        output = tmp_path / f"cue-{index}.mp3"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:sample_rate=32000",
                "-t",
                "0.45",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        chunks.append(
            {
                "cue_id": f"cue-{index}",
                "index": index,
                "start": start,
                "end": start + 0.6,
                "audio_duration": 0.45,
                "audio_bytes": output.read_bytes(),
            }
        )

    audio, detail = asyncio.run(bot.build_dub_timeline_audio(chunks, 2.0))
    qc = asyncio.run(bot.subdub_validate_tts_timeline_audio_bytes(audio))

    assert audio
    assert "sequential=yes" in detail
    assert "overlap_count=0" in detail
    assert qc["ok"] is True
    assert qc["duration"] == pytest.approx(2.0, abs=0.08)


def test_dub_timeline_extends_output_instead_of_cutting_spoken_sentence(monkeypatch):
    commands = []

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"full-spoken-sentence")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)

    output, detail = asyncio.run(
        bot.build_dub_timeline_audio(
            [{"cue_id": "cue-1", "start": 0.0, "end": 2.0, "audio_duration": 5.0, "audio_bytes": b"voice"}],
            2.0,
        )
    )

    assert output == b"full-spoken-sentence"
    assert "timeline_extended=yes" in detail
    assert "source_duration=2.000" in detail
    assert "duration=4.348" in detail
    assert "full_speech=yes" in detail
    filter_graph = commands[-1][commands[-1].index("-filter_complex") + 1]
    assert "atempo=1.150000" in filter_graph
    assert "atrim=duration=2.000" not in filter_graph
    assert commands[-1][commands[-1].index("-t") + 1] == "4.348"


def test_subdub_renderer_freezes_last_frame_for_extended_dub_without_changing_ratio(monkeypatch):
    commands = []

    async def fake_probe(_payload):
        return {
            "ok": True,
            "duration": 2.0,
            "has_video": True,
            "has_audio": True,
            "width": 1080,
            "height": 1920,
        }

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"validated-mp4")
        return True, "ok"

    async def fake_validate(payload, *, require_audio=False, expected_duration=0.0, **_kwargs):
        assert payload == b"validated-mp4"
        assert require_audio is True
        assert expected_duration == pytest.approx(4.348)
        return {
            "ok": True,
            "detail": "ok",
            "duration": 4.348,
            "actual_duration": 4.348,
            "has_video": True,
            "has_audio": True,
        }

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"source-video",
            dubbed_audio=b"full-dub-audio",
            subtitle_style={"show_subtitles": False},
            target_duration_seconds=4.348,
            require_audio=True,
        )
    )

    assert output == b"validated-mp4"
    command = commands[-1]
    video_filter = command[command.index("-vf") + 1]
    assert "tpad=stop_mode=clone:stop_duration=2.348" in video_filter
    assert "scale=" not in video_filter
    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "4.348"
    assert "source_duration=2.000" in detail
    assert "render_duration=4.348" in detail
    assert "video_extended_by=2.348" in detail


def test_subdub_renderer_real_ffmpeg_extension_keeps_vertical_frame_and_audible_audio(tmp_path):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    source = tmp_path / "source-vertical.mp4"
    dub = tmp_path / "dub.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x568:r=25:d=2",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=32000:duration=2",
            "-t", "2.000",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=32000:duration=4",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(dub),
        ],
        check=True,
        capture_output=True,
    )

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            source.read_bytes(),
            dubbed_audio=dub.read_bytes(),
            subtitle_style={"show_subtitles": False},
            target_duration_seconds=4.0,
            require_audio=True,
        )
    )
    probe = asyncio.run(bot.subdub_probe_video_bytes(output))
    activity = asyncio.run(bot.subdub_audio_activity_metrics(output))

    assert output
    assert probe["ok"] is True
    assert probe["duration"] == pytest.approx(4.0, abs=0.12)
    assert probe["width"] == 320
    assert probe["height"] == 568
    assert bot.subdub_aspect_ratio_close(320, 568, probe["width"], probe["height"])
    assert probe["has_audio"] is True
    assert activity["ok"] is True
    assert activity["non_silent_seconds"] >= 3.5
    assert "video_extended_by=2.000" in detail


def test_product_pipeline_blocks_mp4_when_generated_tts_qc_fails():
    render_calls = []

    async def prepare(state):
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Hello"}],
            "output_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            "output_script": "Xin chao",
        }

    async def synthesize(*_args, **_kwargs):
        return {
            "provider": "key4u_minimax",
            "chunks": [{"index": 1, "start": 0.0, "end": 2.0, "audio_duration": 2.0, "audio_bytes": b"click"}],
        }

    async def timeline(*_args, **_kwargs):
        return b"click-track", "sequential"

    async def normalize(*_args, **_kwargs):
        return b"click-track", "normalized"

    async def validate_audio(*_args, **_kwargs):
        return {"ok": False, "detail": "speech_activity_missing", "duration": 2.0, "audio_bytes": 11}

    async def render(*_args, **_kwargs):
        render_calls.append(True)
        return b"fake-mp4", "rendered"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"video_duration": 2, "output_type": "video", "target_language": "vi"},
            user_id=42,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "Vietnamese_female_4_v1",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=normalize,
            validate_audio=validate_audio,
            render_video=render,
            video_render_ready=lambda *_args: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "TTS_AUDIO_QC_FAILED"
    assert result["error_code"] == "speech_activity_missing"
    assert render_calls == []


def test_product_pipeline_passes_full_spoken_timeline_to_subdub_renderer():
    render_calls = []

    async def prepare(state):
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Hello"}],
            "output_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao day la mot cau dai"}],
            "output_script": "Xin chao day la mot cau dai",
        }

    async def synthesize(*_args, **_kwargs):
        return {
            "provider": "key4u_minimax",
            "chunks": [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "audio_duration": 5.0,
                    "audio_bytes": b"spoken-sentence",
                }
            ],
        }

    async def timeline(*_args, **_kwargs):
        return (
            b"full-timeline-audio",
            "ffmpeg_sequential_timeline_audio:cues=1;duration=4.348;"
            "source_duration=2.000;timeline_extended=yes;full_speech=yes",
        )

    async def normalize(audio):
        assert audio == b"full-timeline-audio"
        return audio, "normalized"

    async def validate_audio(audio):
        assert audio == b"full-timeline-audio"
        return {
            "ok": True,
            "detail": "speech_activity_ok",
            "duration": 4.348,
            "audio_bytes": len(audio),
        }

    async def render(_source, **kwargs):
        render_calls.append(dict(kwargs))
        return b"final-mp4", "rendered"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"video_duration": 2, "output_type": "video", "target_language": "vi"},
            user_id=42,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "Vietnamese_female_4_v1",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=normalize,
            validate_audio=validate_audio,
            render_video=render,
            video_render_ready=lambda *_args: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["video_output"] == b"final-mp4"
    assert result["tts_timeline_duration"] == pytest.approx(4.348)
    assert result["final_video_expected_duration"] == pytest.approx(4.348)
    assert render_calls[0]["target_duration_seconds"] == pytest.approx(4.348)


def test_core_uses_extended_dub_duration_for_final_validation_and_delivery():
    product_result = {
        "video_output": b"final-mp4",
        "final_video_expected_duration": 37.337,
        "tts_timeline_duration": 37.337,
    }

    assert bot.subdub_final_expected_duration_seconds(
        29.0,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        product_result,
    ) == pytest.approx(37.337)
    assert bot.subdub_final_expected_duration_seconds(
        29.0,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        product_result,
    ) == pytest.approx(37.337)
    assert bot.subdub_final_expected_duration_seconds(
        29.0,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        product_result,
    ) == pytest.approx(29.0)

    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subdub_final_expected_duration_seconds(" in core_source
    assert "expected_duration=final_video_expected_duration_seconds" in core_source
    assert "expected_duration_seconds=final_video_expected_duration_seconds" in core_source


def test_key4u_minimax_forwards_resolved_international_language_boost(monkeypatch):
    captured = {}

    class Provider:
        async def tts(self, text, **kwargs):
            captured["text"] = text
            captured.update(kwargs)
            return {"ok": True, "status": "PASS", "http_status": 200, "output_bytes": b"audio"}

    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda **_kwargs: True)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Provider())

    status, audio, _detail, _http = asyncio.run(
        bot.key4u_minimax_tts_bytes(
            "Konnichiwa",
            voice_id="Japanese_KindVoice_v1",
            tts_language_boost="Japanese",
            allow_admin=True,
        )
    )

    assert status == "PASS"
    assert audio == b"audio"
    assert captured["language_boost"] == "Japanese"


def test_all_minimax_payloads_preserve_resolved_international_language_boost(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_VOICE", "Japanese_KindVoice_v1")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_FEMALE_VOICE", "Japanese_KindVoice_v1")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_MALE_VOICE", "Japanese_KindVoice_v1")

    direct = bot.minimax_tts_payload(
        "Konnichiwa",
        voice_id="Japanese_KindVoice_v1",
        tts_language_boost="Japanese",
    )
    shopaikey = bot.shopaikey_official_tts_payload(
        "Konnichiwa",
        voice_id="Japanese_KindVoice_v1",
        tts_language_boost="Japanese",
    )

    assert direct["language_boost"] == "Japanese"
    assert shopaikey["language_boost"] == "Japanese"


def test_subdub_debug_persists_generated_audio_truth():
    payload = bot.subtitle_dub_debug_job_payload(
        user_id=42,
        chat_id=42,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={
            "tts_audio_bytes": 8192,
            "tts_audio_qc": {"ok": True, "detail": "speech_activity_ok", "duration": 3.25},
            "_subdub_generated_audio_duration": 3.25,
        },
        status="completed",
        stage="delivered",
    )

    assert payload["audio_bytes"] == 8192
    assert payload["tts_audio_qc"]["ok"] is True
    assert payload["generated_audio_duration"] == pytest.approx(3.25)


def test_legacy_dubbing_mux_does_not_use_shortest():
    assert "-shortest" not in inspect.getsource(dubbing_pipeline.mux_final_video)


def test_tts_activity_reports_leading_and_trailing_silence(tmp_path):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    output = tmp_path / "speech-with-boundary-silence.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=32000:duration=0.5",
            "-af",
            "adelay=250|250,apad=whole_dur=1.100,atrim=duration=1.100",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output),
        ],
        check=True,
        capture_output=True,
    )

    metrics = asyncio.run(bot.subdub_audio_activity_metrics(output.read_bytes()))

    assert metrics["ok"] is True
    assert metrics["leading_silence_seconds"] == pytest.approx(0.25, abs=0.10)
    assert metrics["trailing_silence_seconds"] == pytest.approx(0.35, abs=0.12)


def test_tts_chunks_use_spoken_window_without_cutting_speech(monkeypatch):
    async def fake_tts(*_args, **_kwargs):
        return "key4u_minimax", b"valid-audio", "http=200"

    async def fake_qc(*_args, **_kwargs):
        return {
            "ok": True,
            "detail": "speech_activity_ok",
            "duration": 2.0,
            "leading_silence_seconds": 0.25,
            "trailing_silence_seconds": 0.35,
            "non_silent_seconds": 1.4,
            "active_ratio": 0.7,
        }

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "subdub_validate_tts_audio_bytes", fake_qc)

    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}],
            voice_id="female-shaonv",
            allow_admin=True,
            require_speech_qc=True,
        )
    )

    chunk = result["chunks"][0]
    assert chunk["raw_audio_duration"] == pytest.approx(2.0)
    assert chunk["trim_start"] == pytest.approx(0.21)
    assert chunk["trim_end"] == pytest.approx(1.69)
    assert chunk["audio_duration"] == pytest.approx(1.48)


def test_dub_timeline_applies_boundary_trim_before_tempo(monkeypatch):
    commands = []

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"trimmed-sequential-audio")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)

    output, detail = asyncio.run(
        bot.build_dub_timeline_audio(
            [
                {
                    "cue_id": "cue-1",
                    "start": 0.0,
                    "end": 2.0,
                    "raw_audio_duration": 2.0,
                    "audio_duration": 1.48,
                    "trim_start": 0.21,
                    "trim_end": 1.69,
                    "audio_bytes": b"voice",
                }
            ],
            2.0,
        )
    )

    assert output == b"trimmed-sequential-audio"
    assert "sequential=yes" in detail
    filter_graph = commands[-1][commands[-1].index("-filter_complex") + 1]
    assert "atrim=start=0.210000:end=1.690000" in filter_graph
    assert filter_graph.index("atrim=start=0.210000:end=1.690000") < filter_graph.index("afade=t=in")


def test_product_pipeline_preserves_timeline_failure_evidence():
    async def prepare(state):
        segments = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": segments,
            "output_segments": segments,
            "output_script": "Xin chao",
        }

    async def synthesize(*_args, **_kwargs):
        return {
            "provider": "key4u_minimax",
            "chunks": [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "audio_duration": 4.0,
                    "audio_bytes": b"spoken-audio",
                    "audio_qc": {"ok": True, "duration": 4.0},
                }
            ],
        }

    async def timeline(*_args, **_kwargs):
        return b"", "tts_timeline_exceeds_source:required_end=3.478;source_duration=2.000;max_tempo=1.150"

    async def normalize(*_args, **_kwargs):
        raise AssertionError("normalization must not run without timeline audio")

    async def render(*_args, **_kwargs):
        raise AssertionError("render must not run without timeline audio")

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"video_duration": 2, "output_type": "video", "target_language": "original"},
            user_id=42,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "female-shaonv",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=normalize,
            validate_audio=lambda *_args: {"ok": True},
            render_video=render,
            video_render_ready=lambda *_args: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "NO_AUDIO_BYTES"
    assert result["timeline_detail"].startswith("tts_timeline_exceeds_source")
    assert result["tts_provider"] == "key4u_minimax"
    assert result["tts_expected_segments"] == 1
    assert result["tts_generated_segments"] == 1
    assert result["tts_dropped_segments"] == 0


def test_subdub_status_back_returns_to_four_lane_menu_without_ui_copy_change():
    keyboard = bot.subdub_progress_keyboard("ABC123", "vi")

    assert keyboard.inline_keyboard[1][0].text == "⬅️ Quay lại"
    assert keyboard.inline_keyboard[1][0].callback_data == "videodub|status_back_type"
    assert bot.product_progress_status.product_progress_spec("subdub")["back_callback"] == "videodub|status_back_type"
    matching_edges = bot.workflow_graph_contract.build_p0_infra1_workflow_graph().matching_edges("videodub|status_back_type")
    assert any(
        edge.source_node == "subdub_status"
        and edge.target_node == "subdub_start"
        and edge.action_type == "render_only"
        and not edge.provider_allowed
        and not edge.wallet_allowed
        and not edge.reprocess_allowed
        for edge in matching_edges
    )


def test_subdub_status_back_preserves_pending_job_and_artifacts(monkeypatch):
    user_id = 949494
    pending_key = bot.video_dubbing_pending_key(user_id)
    artifact_key = f"video_dubbing_artifact:{user_id}:source"
    original_pending = {
        "origin": "translation",
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "telegram-file",
    }
    bot.USER_PENDING[pending_key] = dict(original_pending)
    bot.USER_PENDING[artifact_key] = {"bytes": b"source-video"}
    captured = {}

    class Query:
        data = "videodub|status_back_type"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)

        async def answer(self, *_args, **_kwargs):
            return None

    async def fake_edit(_query, text, **kwargs):
        captured["text"] = text
        captured["markup"] = kwargs.get("reply_markup")
        return "rendered"

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "safe_edit_or_send", fake_edit)
    try:
        result = asyncio.run(
            bot.handle_video_dubbing_callback(
                SimpleNamespace(callback_query=Query()),
                SimpleNamespace(),
            )
        )

        assert result == "rendered"
        assert bot.USER_PENDING[pending_key] == original_pending
        assert bot.USER_PENDING[artifact_key]["bytes"] == b"source-video"
        callbacks = [
            button.callback_data
            for row in captured["markup"].inline_keyboard
            for button in row
        ]
        assert "videodub|type|subtitle_create" in callbacks
        assert "videodub|type|subtitle_translate" in callbacks
        assert "videodub|type|dub" in callbacks
        assert "videodub|type|subtitle_plus_dub" in callbacks
    finally:
        bot.USER_PENDING.pop(pending_key, None)
        bot.USER_PENDING.pop(artifact_key, None)


def test_tts_activity_does_not_trim_short_audible_boundary_markers(tmp_path):
    ffmpeg = bot.frame_video_ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    output = tmp_path / "audible-boundary-markers.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=32000:duration=0.03",
            "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono:d=0.25",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000:duration=3.0",
            "-f", "lavfi", "-i", "anullsrc=r=32000:cl=mono:d=0.25",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=32000:duration=0.03",
            "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(output),
        ],
        check=True,
        capture_output=True,
    )

    metrics = asyncio.run(bot.subdub_audio_activity_metrics(output.read_bytes()))

    assert metrics["ok"] is True
    assert metrics["leading_silence_seconds"] == 0.0
    assert metrics["trailing_silence_seconds"] == 0.0


def test_core_failure_persists_timeline_detail_and_cue_counts(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "video_dubbing_product_gate_matrix", lambda *_args, **_kwargs: {"product_route_allowed": True})
    monkeypatch.setattr(bot, "video_dubbing_product_gate_allows_pipeline", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "calculate_video_translate_price", lambda *_args, **_kwargs: {"total_price_xu": 0})
    monkeypatch.setattr(bot, "video_dubbing_tts_price_estimate", lambda *_args, **_kwargs: {"price_xu": 0})
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (999999, 0, 0))

    async def fake_save_input(*_args, **_kwargs):
        return {
            "ok": True,
            "path": str(source),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "size": source.stat().st_size,
            "duration": 2,
            "file_saved": True,
            "exists": True,
        }

    async def fake_duration_gate(*_args, **_kwargs):
        return {
            "input_duration": 2,
            "telegram_duration": 2,
            "ffprobe_duration": 2,
            "detected_duration_source": "fixture",
            "duration_gate_result": "pass",
            "duration_limit": 3600,
        }

    async def fake_media_preflight(video_bytes, *, content_type="video/mp4"):
        return {
            "ok": True,
            "normalized": False,
            "normalization_count": 0,
            "source_bytes": bytes(video_bytes),
            "content_type": content_type,
            "source_sha256": "fixture-source",
            "normalized_sha256": "fixture-source",
            "source_duration": 2.0,
            "normalized_duration": 2.0,
            "source_probe": {
                "ok": True,
                "duration": 2.0,
                "normalization_required": False,
            },
        }

    async def fake_blackbox(**_kwargs):
        return {
            "ok": False,
            "status": "NO_AUDIO_BYTES",
            "error_code": "dub_audio_empty",
            "timeline_detail": "tts_timeline_exceeds_source:required_end=3.478;source_duration=2.000;max_tempo=1.150",
            "tts_provider": "key4u_minimax",
            "tts_expected_segments": 2,
            "tts_generated_segments": 2,
            "tts_mixed_segments": 0,
            "tts_dropped_segments": 0,
            "tts_timeline_duration": 2.0,
            "tts_cue_qc": [{"ok": True}, {"ok": True}],
            "state": dict(_kwargs.get("state") or {}),
            "route_attempts": {"tts": True, "mux": False},
        }

    monkeypatch.setattr(bot, "video_dubbing_save_input_for_pipeline", fake_save_input)
    monkeypatch.setattr(bot, "subdub_normalize_video_bytes_if_needed", fake_media_preflight)
    monkeypatch.setattr(bot, "subdub_duration_gate_payload_for_saved_input", fake_duration_gate)
    monkeypatch.setattr(bot.subdub_blackboxes, "run_subdub_lane_blackbox", fake_blackbox)

    class Query:
        from_user = SimpleNamespace(id=949495)
        message = SimpleNamespace(chat_id=949495)

    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "process_type": bot.VIDEO_SUBTITLE_MODE_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "telegram-file",
        "source_file_name": "source.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": 2,
        "source_duration": 2,
        "target_language": "original",
        "subdub_final_confirmed": True,
        "_pipeline_workspace": str(tmp_path / "workspace"),
    }

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            Query(),
            SimpleNamespace(),
            state,
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is False
    assert result["detail"].startswith("tts_timeline_exceeds_source")
    assert result["state"]["tts_expected_segments"] == 2
    assert result["state"]["tts_generated_segments"] == 2
    assert result["debug_job"]["tts_expected_segments"] == 2
    assert result["debug_job"]["tts_generated_segments"] == 2
    assert result["debug_job"]["tts_timeline_detail"].startswith("tts_timeline_exceeds_source")
