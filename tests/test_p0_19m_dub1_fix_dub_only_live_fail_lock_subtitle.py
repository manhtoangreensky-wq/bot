import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao the gioi\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao the gioi"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-dub1" + b"x" * 4096


class CaptureMessage:
    chat_id = 1901

    def __init__(self):
        self.calls = []

    def _message(self):
        return SimpleNamespace(message_id=100 + len(self.calls), chat_id=self.chat_id)

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", text, kwargs))
        return self._message()

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return self._message()

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return self._message()

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return self._message()


def test_dub1_subtitle_only_live_pass_delivery_locked_no_auto_srt():
    message = CaptureMessage()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=[{"bytes": VALID_SRT.encode("utf-8"), "filename": "translated.srt", "caption": "SRT"}],
            srt_text=VALID_SRT,
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=True,
        )
    )

    assert result["final_mp4_delivered"] is True
    assert result["srt_auto_send_suppressed"] is True
    assert result["explicit_srt_download_available"] is True
    assert [kind for kind, *_ in message.calls] == ["video"]


def test_dub1_dub_only_render_reencodes_when_copy_mux_fails(monkeypatch):
    calls = []

    async def fake_run_ffmpeg_command(command, timeout=120):
        calls.append(list(command))
        output_path = Path(command[-1])
        if len(calls) == 1:
            return False, "copy mux failed"
        output_path.write_bytes(MP4_BYTES)
        return True, "ok"

    async def fake_probe(_video_bytes):
        return {"ok": True, "has_video": True, "has_audio": True, "width": 320, "height": 240, "duration": 2.0}

    async def fake_validate(_video_bytes, *, require_audio=False, min_bytes=None):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_audio": bool(require_audio)}

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run_ffmpeg_command)
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"source-video",
            dubbed_audio=b"dub-audio",
            subtitle_bytes=b"",
            require_audio=True,
        )
    )

    assert output == MP4_BYTES
    assert len(calls) == 2
    assert "libx264" in calls[1]
    assert "basic_reencode" in detail
    assert "basic_copy_fallback" in detail


async def _run_dub_core(*, render_video):
    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "output_script": "Xin chao the gioi",
            "output_segments": list(VALID_SEGMENTS),
            "asr_provider": "fixture_asr",
        }

    async def synthesize_segments(_segments, **_kwargs):
        return {"provider": "fixture_tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"voice"}]}

    async def build_timeline_audio(_chunks, *_args, **_kwargs):
        return b"dub-audio", "timeline"

    async def normalize_audio(audio_bytes):
        return bytes(audio_bytes or b""), "normalized"

    return await subtitle_dub_product_pipeline.run_subdub_pipeline(
        job_id="dub1",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={"output_type": "video", "video_duration": "2", "voice_kind": "default_female"},
        user_id=1,
        prepare_subtitles=prepare_subtitles,
        srt_from_text=bot.video_dubbing_srt_from_text,
        segments_from_text=bot.video_dubbing_segments_from_text,
        segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
        subtitle_output_items=bot.video_dubbing_subtitle_output_items,
        resolve_voice_id=lambda _uid, _state: "female-real-voice",
        parse_voice_speed=lambda _value: 1.0,
        synthesize_segments=synthesize_segments,
        build_timeline_audio=build_timeline_audio,
        normalize_audio=normalize_audio,
        render_video=render_video,
        video_render_ready=lambda _output_type: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    )


def test_dub1_dub_only_happy_path_fixture_returns_mp4():
    async def render_video(_source, **kwargs):
        assert kwargs.get("dubbed_audio") == b"dub-audio"
        assert kwargs.get("subtitle_bytes") == b""
        return MP4_BYTES, "ffmpeg_video_render_basic:ok"

    result = asyncio.run(_run_dub_core(render_video=render_video))

    assert result["ok"] is True
    assert result["product_type"] == "dub_only"
    assert result["video_output"] == MP4_BYTES
    assert result["partial_result"] is False
    assert result["route_attempts"]["render"] is True


def test_dub1_dub_only_mux_fail_is_clean_no_mp4_no_success():
    async def render_video(_source, **_kwargs):
        return b"", "mux failed"

    result = asyncio.run(_run_dub_core(render_video=render_video))

    assert result["ok"] is True
    assert result["partial_result"] is True
    assert result["video_output"] == b""
    assert result["audio_bytes"] == b"dub-audio"
    assert result["partial_reason"] == "video_render_unavailable"


def test_dub1_required_debug_fields_present(tmp_path):
    source_path = tmp_path / "source.mp4"
    audio_path = tmp_path / "dub.mp3"
    final_path = tmp_path / "final.mp4"
    source_path.write_bytes(b"source")
    audio_path.write_bytes(b"audio")
    final_path.write_bytes(MP4_BYTES)

    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=2,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={
            "_pipeline_job_id": "DUB1DEBUG",
            "_subdub_generated_audio_duration": 2.0,
            "video_delivery_message_id": "777",
            "success_sent_count": 1,
            "terminal_public_outcome_type": "success",
            "final_mp4_validated": True,
            "final_mp4_delivered": True,
        },
        status="completed",
        stage="delivered",
        input_save={"ok": True, "path": str(source_path), "size": source_path.stat().st_size},
        workspace_artifacts={"dub_audio": str(audio_path), "final_mp4": str(final_path)},
        detail="",
        pipeline_attempted=True,
        route_attempts={"render": True, "transcript_length": 12, "tts": True},
    )

    for key in (
        "mode",
        "job_id",
        "source_video_received",
        "transcript_created",
        "translated_text_created",
        "tts_audio_created",
        "tts_audio_duration",
        "mux_invoked",
        "mux_output_exists",
        "mux_output_valid",
        "mp4_sent",
        "receipt_sent",
        "failure_sent",
        "terminal_state",
        "fail_reason",
        "subtitle_only_locked",
        "dub_only_path",
    ):
        assert key in payload

    assert payload["dub_only_path"] is True
    assert payload["source_video_received"] is True
    assert payload["tts_audio_created"] is True
    assert payload["mux_output_valid"] is True
    assert payload["mp4_sent"] is True
    assert payload["receipt_sent"] is True
    assert payload["failure_sent"] is False
    text = bot.subdub_job_debug_text(payload, "DUB1DEBUG")
    assert "source_video_received" in text
    assert "mux_output_valid" in text
    assert "dub_only_path" in text


def test_dub1_no_raw_audio_or_file_autosend_when_mp4_missing(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED", False)
    message = CaptureMessage()

    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"internal-audio",
            video_bytes=b"",
            include_subtitle_outputs=False,
        )
    )

    assert result["terminal_public_outcome_type"] == "failure"
    assert result["audio_artifact_internal_only"] is True
    assert message.calls == []
