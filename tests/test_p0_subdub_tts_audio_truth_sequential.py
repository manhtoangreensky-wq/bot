import asyncio
import inspect
import subprocess
from pathlib import Path

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


def test_dub_timeline_does_not_cut_sentence_that_cannot_fit_naturally(monkeypatch):
    async def fake_run(command, timeout=0):
        del timeout
        Path(command[-1]).write_bytes(b"must-not-be-accepted")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)

    output, detail = asyncio.run(
        bot.build_dub_timeline_audio(
            [{"cue_id": "cue-1", "start": 0.0, "end": 2.0, "audio_duration": 5.0, "audio_bytes": b"voice"}],
            2.0,
        )
    )

    assert output == b""
    assert "tts_timeline_exceeds_source" in detail
    assert "max_tempo=1.150" in detail


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
    assert keyboard.inline_keyboard[1][0].callback_data == "videodub|back_type"
    assert bot.product_progress_status.product_progress_spec("subdub")["back_callback"] == "videodub|back_type"
    matching_edges = bot.workflow_graph_contract.build_p0_infra1_workflow_graph().matching_edges("videodub|back_type")
    assert any(
        edge.source_node == "subdub_status"
        and edge.target_node == "subdub_start"
        and not edge.provider_allowed
        and not edge.wallet_allowed
        and not edge.reprocess_allowed
        for edge in matching_edges
    )
