import inspect
from pathlib import Path

import bot
from services import provider_gate
from services import subtitle_dub_pipeline as pipeline


def _storyboard():
    return {
        "scene_cards": [
            {"scene_index": 1, "narration_line": "Mở đầu video bằng vấn đề chính.", "start": 0, "end": 4},
            {"scene_index": 2, "narration_line": "Giải thích lợi ích bằng ví dụ rõ ràng.", "start": 4, "end": 9},
            {"scene_index": 3, "narration_line": "Kết thúc bằng lời kêu gọi hành động.", "start": 9, "end": 14},
        ]
    }


def _fake_tts(text, voice_id="", output_path="", **_kwargs):
    payload = f"FAKE-DUB-AUDIO:{voice_id}:{text}".encode("utf-8")
    if output_path:
        Path(output_path).write_bytes(payload)
    return payload


def _fake_mux(video_path, audio_path, output_path, subtitle_path=""):
    assert Path(video_path).stat().st_size > 0
    assert Path(audio_path).stat().st_size > 0
    assert pipeline.validate_srt(subtitle_path)
    Path(output_path).write_bytes(b"FAKE-MP4\n" + Path(video_path).read_bytes()[:32] + Path(audio_path).read_bytes()[:32])
    return output_path


def _fake_mux_fail(*_args, **_kwargs):
    raise RuntimeError("mux_failed")


def test_subtitle_from_storyboard_generates_valid_srt():
    transcript = pipeline.build_transcript_from_storyboard(_storyboard(), scene_duration=5)
    srt = pipeline.generate_srt_from_transcript(transcript)
    assert len(transcript) == 3
    assert pipeline.validate_srt(srt)
    assert "00:00:04,000 --> 00:00:09,000" in srt


def test_subtitle_from_narration_generates_valid_srt():
    transcript = pipeline.build_transcript_from_storyboard({}, narration_text="Dòng thứ nhất\nDòng thứ hai", scene_duration=3)
    srt = pipeline.generate_srt_from_transcript(transcript)
    assert pipeline.validate_srt(srt)
    assert "00:00:03,000 --> 00:00:06,000" in srt


def test_srt_timestamps_valid():
    valid = pipeline.generate_srt_from_transcript([{"start": 0, "end": 2.5, "text": "Xin chào"}])
    assert pipeline.validate_srt(valid)
    assert not pipeline.validate_srt("1\n00:00:02,000 --> 00:00:01,000\nSai thứ tự\n")
    assert not pipeline.validate_srt("1\nbad timestamp\nThiếu mốc\n")


def test_translate_srt_preserves_timestamps():
    source = pipeline.generate_srt_from_transcript([
        {"start": 0, "end": 2, "text": "Xin chào"},
        {"start": 2, "end": 5, "text": "Hẹn gặp lại"},
    ])
    translated = pipeline.translate_srt_preserve_timestamps(
        source,
        "English",
        translate_func=lambda text, lang: f"{lang}: {text}",
    )
    assert [line for line in source.splitlines() if "-->" in line] == [
        line for line in translated.splitlines() if "-->" in line
    ]
    assert "English: Xin chào" in translated
    assert pipeline.validate_srt(translated)


def test_dub_pipeline_creates_audio_artifact(tmp_path):
    transcript = pipeline.build_transcript_from_storyboard(_storyboard())
    result = pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
    )
    assert result.ok is True
    assert result.audio_path
    assert Path(result.audio_path).stat().st_size > 0
    assert result.result_type == "audio_subtitle"


def test_dub_pipeline_mux_success_returns_mp4(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"REAL-ENOUGH-SOURCE-MP4")
    transcript = pipeline.build_transcript_from_storyboard(_storyboard())
    result = pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path / "out"),
        source_video_path=str(source_video),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
        mux_func=_fake_mux,
    )
    assert result.ok is True
    assert result.result_type == "mp4"
    assert result.video_path
    assert Path(result.video_path).stat().st_size > 0


def test_dub_pipeline_mux_failure_returns_partial(tmp_path):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"REAL-ENOUGH-SOURCE-MP4")
    transcript = pipeline.build_transcript_from_storyboard(_storyboard())
    result = pipeline.run_dub_pipeline(
        workspace_dir=str(tmp_path / "out"),
        source_video_path=str(source_video),
        transcript=transcript,
        provider_voice_id="voice-ready-1",
        tts_func=_fake_tts,
        mux_func=_fake_mux_fail,
    )
    assert result.ok is True
    assert result.result_type == "partial"
    assert result.audio_path and Path(result.audio_path).stat().st_size > 0
    assert result.subtitle_path and pipeline.validate_srt(result.subtitle_path)
    assert not result.video_path


def test_uploaded_video_subtitle_guard_no_false_success():
    state = {
        "source_file_id": "fake-uploaded-video",
        "video_file_id": "fake-uploaded-video",
        "source_file_name": "uploaded.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
    }
    decision = bot.video_dubbing_engine_access_decision(
        0,
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        state,
        is_paid_job=True,
        confirm_paid=False,
    )
    assert decision["allowed"] is False
    assert "success" not in str(decision).lower()
    assert provider_gate.public_copy_has_technical_terms(decision.get("message", "")) is False
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "cmd_tool_test_uploaded_video_subtitle_guard" in source
    assert r"^/tool_test_uploaded_video_subtitle_guard" in source


def test_no_provider_before_confirm():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    preconfirm = source.split("confirm_modes = {", 1)[0]
    forbidden = [
        "execute_video_dubbing_pipeline",
        "video_dubbing_prepare_subtitles",
        "video_dubbing_transcribe_bytes",
        "translate_subtitle_text",
        "video_dubbing_tts_bytes",
    ]
    assert all(item not in preconfirm for item in forbidden)


def test_no_charge_before_confirm():
    callback_source = inspect.getsource(bot.handle_video_dubbing_callback)
    preconfirm = callback_source.split("confirm_modes = {", 1)[0]
    assert "spend_fixed_credit_info" not in preconfirm
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert core_source.index("video_dubbing_engine_access_decision") < core_source.index("video_dubbing_prepare_subtitles")
    assert core_source.index("video_dubbing_prepare_subtitles") < core_source.index("spend_fixed_credit_info")


def test_public_copy_no_raw_ffmpeg_provider():
    texts = [
        provider_gate.PUBLIC_SAFE_BLOCK_MESSAGE,
        provider_gate.PUBLIC_SAFE_NOT_READY_MESSAGE,
        provider_gate.safe_public_error("provider API FFmpeg traceback token failed"),
        pipeline.PUBLIC_PARTIAL_MESSAGE,
        pipeline.PUBLIC_SAFE_ERROR,
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {}, "vi", admin=False),
    ]
    assert all(not provider_gate.public_copy_has_technical_terms(text) for text in texts)
