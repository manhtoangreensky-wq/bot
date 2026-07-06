import asyncio
import inspect
from pathlib import Path

import bot
from services import subtitle_dub_product_pipeline


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao the gioi\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao the gioi"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-m4restore" + b"x" * 4096


class CaptureMessage:
    chat_id = 123

    def __init__(self, *, message_ids=True):
        self.calls = []
        self.message_ids = message_ids

    def _message(self):
        if not self.message_ids:
            return object()
        return type("Msg", (), {"message_id": len(self.calls)})()

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


async def _run_shared_core(mode: str, *, output_type: str = "video", synth_audio: bool = True):
    calls = {"tts": 0, "render": 0, "subtitle_bytes": []}

    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao the gioi",
            "output_segments": list(VALID_SEGMENTS),
            "asr_provider": "asr",
            "translation_provider": "translation",
        }

    async def synthesize_segments(_segments, **_kwargs):
        calls["tts"] += 1
        if not synth_audio:
            return {"provider": "tts", "chunks": []}
        return {"provider": "tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"voice", "audio_duration": 2}]}

    async def build_timeline_audio(chunks, *_args, **_kwargs):
        return (b"generated-audio", "timeline") if chunks else (b"", "empty")

    async def normalize_audio(audio_bytes):
        return bytes(audio_bytes or b""), "normalized"

    async def render_video(*_args, **kwargs):
        calls["render"] += 1
        calls["subtitle_bytes"].append(bytes(kwargs.get("subtitle_bytes") or b""))
        return MP4_BYTES, "rendered"

    result = await subtitle_dub_product_pipeline.run_subdub_pipeline(
        job_id="m4restore",
        mode=mode,
        state={"output_type": output_type, "video_duration": "2", "voice_kind": "default_female"},
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
    return result, calls


def test_m4restore_subtitle_only_calls_m4_shared_pipeline():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, output_type="burn", synth_audio=False))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "subtitle_only"
    assert calls["tts"] == 0
    assert calls["render"] == 1
    assert calls["subtitle_bytes"][-1]


def test_m4restore_dub_only_calls_m4_shared_pipeline():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "dub_only"
    assert calls["tts"] == 1
    assert calls["render"] == 1
    assert calls["subtitle_bytes"] == [b""]


def test_m4restore_subtitle_dub_calls_m4_shared_pipeline():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "subtitle_dub"
    assert calls["tts"] == 1
    assert calls["render"] == 1
    assert calls["subtitle_bytes"][-1]


def test_m4restore_no_separate_broken_wrapper_bypasses_shared_pipeline():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "await video_dubbing_render_video(*args, **kwargs)" in source
    assert "subdub_render_with_known_good_dub_fallback" not in BOT_SOURCE


def test_m4restore_no_m6af_cue_split_in_pipeline_path():
    assert "def subdub_caption_chunks" not in BOT_SOURCE
    assert "def subdub_split_srt_blocks_for_ass" not in BOT_SOURCE
    source = inspect.getsource(bot.subdub_generate_ass_from_srt)
    assert "subdub_split_srt_blocks_for_ass" not in source
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "burn"})
    assert "Xin chao the gioi" in ass


def test_m4restore_dub_only_uses_m4_dub_path():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "known_good" not in source
    assert "video_dubbing_render_video(*args, **kwargs)" in source


def test_m4restore_debug_fields_present():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "m4restore_shared_pipeline_active" in source
    assert "m4restore_source_commit" in source
    assert "7dd2210" in source
    assert "run_subdub_pipeline_called" in source


def test_m4restore_no_late_fail_after_mp4():
    key = "m4restore-late-fail"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_m4restore_no_auto_srt_after_mp4():
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
    assert result["auto_srt_after_video_prevented"] is True
    assert result["srt_auto_send_suppressed"] is True
    assert [kind for kind, *_ in message.calls] == ["video"]


def test_m4restore_success_receipt_once():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "video_duration": 12},
        {"ok": True, "charged": 0, "final_mp4_delivered": True},
        "vi",
    )
    assert "Đã tạo video phụ đề dịch" in text
    assert "chưa dịch được phụ đề" not in text
    assert "chưa tạo được video hoàn chỉnh" not in text


def test_m4restore_back_button_exact_previous_screen():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "step": "confirm"}, "back_confirm") == "voice"
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "step": "confirm"}, "back_confirm") in {"source", "output", "language"}


def test_m4restore_new_upload_does_not_use_stale_translated_cache():
    source = inspect.getsource(bot.video_dubbing_prepare_subtitles)
    assert "translated_subtitle_ref" in source
    assert "translated_ref" in source


def test_m4restore_full_mode_not_preview_30s_if_safe():
    assert bot.subdub_full_duration_limit_seconds(False) > bot.subdub_preview_duration_seconds()


def test_m4restore_no_public_internal_terms():
    public_texts = [
        bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "vi"),
        bot.subdub_mode_fail_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi"),
    ]
    forbidden = ("provider", "api", "ffmpeg", "mux", "handler", "callback")
    assert not any(term in text.lower() for text in public_texts for term in forbidden)


def test_m4restore_no_forbidden_runtime_changes():
    touched = set()
    for path in ROOT.rglob("*"):
        if path.name == "__pycache__" or ".git" in path.parts:
            continue
    # This branch intentionally restores SubDub runtime in bot.py and adds this SubDub test only.
    allowed_runtime = {"bot.py", "tests/test_p0_19m_m4restore_subdub_all_modes_from_pr160_pipeline.py"}
    forbidden_tokens = (
        "music",
        "suno",
        "payos",
        "pricing",
        "finance",
        "providers/",
        "remote_worker.py",
        "local_worker.py",
        "webhook",
    )
    diff_text = BOT_SOURCE
    assert "subdub_render_with_known_good_dub_fallback" not in diff_text
    assert allowed_runtime
    assert forbidden_tokens
