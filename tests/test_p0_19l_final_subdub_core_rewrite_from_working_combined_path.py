import asyncio
import copy
import inspect

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019l" + b"x" * 4096


class CaptureMessage:
    def __init__(self):
        self.chat_id = 123
        self.calls = []

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", text, kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return type("Msg", (), {"message_id": len(self.calls)})()


async def _run_shared_core(mode, *, output_subtitle=VALID_SRT, output_script="Xin chao", output_segments=None, synth_audio=True, output_type="video"):
    output_segments = VALID_SEGMENTS if output_segments is None else output_segments
    calls = {"subtitle_items": 0, "tts": 0, "render": 0, "subtitle_bytes": []}

    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "output_subtitle": output_subtitle,
            "output_script": output_script,
            "output_segments": list(output_segments or []),
            "asr_provider": "asr",
            "translation_provider": "translation",
        }

    def subtitle_items(srt_text, requested_output_type, item_mode):
        calls["subtitle_items"] += 1
        return bot.video_dubbing_subtitle_output_items(srt_text, requested_output_type, item_mode)

    async def synthesize_segments(_segments, **_kwargs):
        calls["tts"] += 1
        if not synth_audio:
            return {"provider": "tts", "chunks": []}
        return {"provider": "tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"voice", "audio_duration": 2}]}

    async def build_timeline_audio(chunks, *_args, **_kwargs):
        if not chunks:
            return b"", "empty"
        return b"generated-audio", "timeline"

    async def normalize_audio(audio_bytes):
        return bytes(audio_bytes or b""), "normalized"

    async def render_video(*_args, **kwargs):
        calls["render"] += 1
        calls["subtitle_bytes"].append(bytes(kwargs.get("subtitle_bytes") or b""))
        return MP4_BYTES, "rendered"

    result = await subtitle_dub_product_pipeline.run_subdub_pipeline(
        job_id="p019l-job",
        mode=mode,
        state={"output_type": output_type, "video_duration": "2", "voice_kind": "default_female"},
        user_id=1,
        prepare_subtitles=prepare_subtitles,
        srt_from_text=bot.video_dubbing_srt_from_text,
        segments_from_text=bot.video_dubbing_segments_from_text,
        segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
        subtitle_output_items=subtitle_items,
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


def _new_job(key):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)


def test_subtitle_only_uses_shared_subdub_core():
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core(bot.VIDEO_SUBTITLE_MODE_CREATE)


def test_dub_only_uses_shared_subdub_core():
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB)


def test_subtitle_dub_uses_shared_subdub_core():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)


def test_no_subdub_mode_uses_legacy_error_path():
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core("legacy_subdub_error") is False


def test_subtitle_only_does_not_require_tts_audio():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_CREATE, synth_audio=False, output_type="burn"))
    assert result["ok"] is True
    assert result["audio_bytes"] == b""
    assert calls["tts"] == 0


def test_subtitle_only_generates_subtitle_artifact():
    result, _calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_CREATE, output_type="burn"))
    assert result["srt_bytes"]
    assert result["subtitle_items"]
    assert result["product_type"] == "subtitle_only"


def test_subtitle_only_success_requires_valid_subtitle_output():
    result, _calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_CREATE, output_subtitle="", output_script="", output_segments=[], output_type="burn"))
    assert result["ok"] is False
    assert result["status"] == "SUBTITLE_EMPTY"


def test_subtitle_only_clean_fail_once():
    key = "p019l-subtitle-fail-once"
    _new_job(key)
    message = CaptureMessage()
    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_CREATE, reason="subtitle_empty"))
    second = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_CREATE, reason="subtitle_empty"))
    assert first["sent"] is True
    assert second["suppressed"] is True
    assert len(message.calls) == 1


def test_dub_only_does_not_render_subtitle_by_default():
    result, calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video"))
    assert result["ok"] is True
    assert calls["render"] == 1
    assert calls["subtitle_bytes"] == [b""]


def test_dub_only_requires_tts_audio():
    result, _calls = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB, synth_audio=False, output_type="video"))
    assert result["ok"] is False
    assert result["status"] == "NO_AUDIO_BYTES"


def test_dub_only_output_requires_audio_stream(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": False, "size": 4096}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    assert asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=True, min_bytes=16))["detail"] == "audio_stream_missing"


def test_dub_only_success_once():
    key = "p019l-dub-success-once"
    _new_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="ok1") is True
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="ok2") is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["subdub_success_message_id"] == "ok1"


def test_subtitle_dub_requires_subtitle_and_tts():
    no_subtitle, _ = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_subtitle="", output_script="", output_segments=[]))
    no_tts, _ = asyncio.run(_run_shared_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, synth_audio=False))
    assert no_subtitle["status"] == "SUBTITLE_EMPTY"
    assert no_tts["status"] == "NO_AUDIO_BYTES"


def test_subtitle_dub_success_once():
    test_dub_only_success_once()


def test_subtitle_dub_no_generic_error_before_success():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    confirm_branch = source[source.find("pending_video_action=action"):source.find("completed_fields =")]
    assert "send_subdub_fail_once" in confirm_branch
    assert "Có lỗi khi xử lý lệnh" not in confirm_branch


def test_delivered_blocks_late_public_fail():
    key = "p019l-delivered-blocks-fail"
    _new_job(key)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, reason="late_error"))
    assert result["suppressed"] is True
    assert message.calls == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["ignored_late_error_count"] == 1


def test_failed_blocks_late_success():
    key = "p019l-failed-blocks-success"
    _new_job(key)
    bot.update_subtitle_dub_pipeline_job(key, terminal_state="failed_no_charge", status="failed")
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is False


def test_delivery_once():
    key = "p019l-delivery-once"
    _new_job(key)
    assert bot.subdub_begin_delivery_once(key) is True
    assert bot.subdub_begin_delivery_once(key) is False


def test_success_message_once():
    test_dub_only_success_once()


def test_generic_subdub_error_suppressed_after_delivered():
    test_delivered_blocks_late_public_fail()


def test_hardsub_cover_height_ratio_default_small():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original"})
    assert 0.02 <= style["cover_height_ratio"] <= 0.06


def test_hardsub_cover_y_ratio_bottom_safe():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original"})
    assert 0.90 <= style["cover_y_ratio"] <= 0.96


def test_hardsub_cover_not_mid_screen():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "cover_y_ratio": 0.70, "cover_height_ratio": 0.24})
    assert style["cover_y_ratio"] >= 0.90
    assert style["cover_height_ratio"] <= 0.06


def test_hardsub_cover_drawbox_or_ass_style_uses_small_bottom_area():
    drawbox = bot.subdub_cover_filter({"subtitle_style_preset": "cover_original"})
    assert "drawbox=" in drawbox
    assert "y=ih*0.90" in drawbox or "y=ih*0.91" in drawbox
    assert "h=ih*0.05" in drawbox or "h=ih*0.06" in drawbox


def test_translated_subtitle_position_over_cover():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, {"subtitle_style_preset": "cover_original"})
    assert "Style: Default" in ass
    assert "Dialogue: 0" in ass
    assert "Xin chao" in ass


def test_selected_female_voice_resolves_female(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ"}
    assert bot.resolve_video_dub_tts_voice_id(1, state) == "female-real-voice"
    assert state["resolved_gender"] == "female"


def test_selected_male_voice_resolves_male(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_male", "voice_style": "Giọng nam"}
    assert bot.resolve_video_dub_tts_voice_id(1, state) == "male-real-voice"
    assert state["resolved_gender"] == "male"


def test_no_silent_female_to_male_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_ALLOW_SILENT_VOICE_FALLBACK", False)
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ"}
    assert bot.resolve_video_dub_tts_voice_id(1, state) == ""
    assert state["_subdub_voice_resolution"]["fallback_used"] is False


def test_missing_female_voice_blocks_or_asks_not_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_ALLOW_SILENT_VOICE_FALLBACK", False)
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ"}
    assert bot.resolve_video_dub_tts_voice_id(1, state) == ""
    assert state["_subdub_voice_resolution"]["ok"] is False


def test_subdub_voice_debug_read_only():
    job = {"selected_voice_gender": "female", "resolved_voice_id": "female-real-voice", "resolved_gender": "female"}
    before = copy.deepcopy(job)
    assert "SUBDUB VOICE DEBUG" in bot.subdub_voice_debug_text(job)
    assert job == before


def test_subtitle_only_progress_no_voice_step():
    labels = [item["label"] for item in bot.subdub_progress_steps_for_product("subtitle_only")]
    assert "Tạo giọng lồng tiếng" not in labels
    assert "Tạo phụ đề" in labels


def test_dub_only_progress_has_voice_step():
    labels = [item["label"] for item in bot.subdub_progress_steps_for_product("dub_only")]
    assert "Chọn giọng lồng tiếng" in labels
    assert "Tạo giọng lồng tiếng" in labels
    assert "Tạo phụ đề" not in labels


def test_combined_progress_has_subtitle_and_voice_steps():
    labels = [item["label"] for item in bot.subdub_progress_steps_for_product("subtitle_dub")]
    assert "Tạo phụ đề" in labels
    assert "Tạo giọng lồng tiếng" in labels


def test_zero_duration_output_blocks_success(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 0.0, "has_video": True, "has_audio": True, "size": 4096}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    assert asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=True, min_bytes=16))["ok"] is False


def test_missing_audio_blocks_dub_success(monkeypatch):
    test_dub_only_output_requires_audio_stream(monkeypatch)


def test_empty_subtitle_blocks_subtitle_success():
    test_subtitle_only_success_requires_valid_subtitle_output()
