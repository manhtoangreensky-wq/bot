import asyncio
import inspect

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chào thế giới\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chào thế giới"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m4" + b"x" * 4096


class CaptureMessage:
    def __init__(self, *, message_ids=True):
        self.chat_id = 123
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


async def _run_core(mode, *, synth_audio=True, output_type="video"):
    calls = {"tts": 0, "render": 0, "subtitle_bytes": []}

    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chào thế giới",
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
        job_id="p019m4",
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


def _new_job(key):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)


def test_subtitle_only_uses_canonical_combined_core_without_tts():
    result, calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, synth_audio=False, output_type="burn"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "subtitle_only"
    assert calls["tts"] == 0
    assert calls["render"] == 1
    assert calls["subtitle_bytes"][-1]


def test_dub_only_uses_canonical_combined_core_without_burned_subtitles():
    result, calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "dub_only"
    assert calls["tts"] == 1
    assert calls["render"] == 1
    assert calls["subtitle_bytes"] == [b""]


def test_subtitle_dub_uses_canonical_combined_core():
    result, calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle"))
    assert result["ok"] is True
    assert result["shared_core_used"] is True
    assert result["product_type"] == "subtitle_dub"
    assert calls["tts"] == 1
    assert calls["subtitle_bytes"][-1]


def test_old_subtitle_route_wrapped_to_canonical_core():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)


def test_old_dub_route_wrapped_to_canonical_core():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert subtitle_dub_product_pipeline.subdub_mode_uses_shared_core(bot.VIDEO_SUBTITLE_MODE_DUB)


def test_no_late_public_error_after_success():
    key = "p019m4-late-error"
    _new_job(key)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, reason="late"))
    assert result["suppressed"] is True
    assert message.calls == []


def test_no_failed_then_success_public_sequence():
    key = "p019m4-failed-then-success"
    _new_job(key)
    message = CaptureMessage()
    first = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="fail"))
    success = bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered")
    assert first["sent"] is True
    assert success is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == "failed_no_charge"


def test_terminal_lock_after_delivery():
    key = "p019m4-terminal-lock"
    _new_job(key)
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is True
    bot.update_subtitle_dub_pipeline_job(key, status="failed", terminal_state="failed_no_charge")
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == "delivered"


def test_success_requires_telegram_message_id():
    message = CaptureMessage(message_ids=False)
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=False,
        )
    )
    assert sent["video"] == 0
    assert sent["video_document"] == 0
    assert sent["telegram_message_id"] == ""


def test_output_preserves_input_aspect_ratio():
    assert bot.subdub_aspect_ratio_close(1080, 1920, 1080, 1920)
    assert bot.subdub_aspect_ratio_close(1920, 1080, 1280, 720)
    assert not bot.subdub_aspect_ratio_close(1920, 1080, 1080, 1080)


def test_output_not_shrunk_into_black_canvas():
    filters = ",".join(bot.subdub_video_fit_filters({"video_width": 1080, "video_height": 1920}))
    assert "pad=" not in filters
    assert "setsar=1" in filters


def test_subdub_video_fit_mode_cover_default():
    assert bot.subdub_video_fit_mode() == "cover"
    assert bot.SUBDUB_KEEP_ORIGINAL_RESOLUTION is True


def test_global_black_cover_disabled_by_default():
    assert bot.SUBDUB_HARDSUB_COVER_ENABLED is False
    state = bot.subdub_output_style_state({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "burn"}, bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    assert state["hardsub_cover_enabled"] is False
    assert bot.subdub_cover_filter(state) == ""


def test_cover_bar_if_enabled_is_small():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "cover_height_ratio": 0.24, "cover_opacity": 0.75})
    assert style["cover_height_ratio"] <= 0.06
    assert style["cover_opacity"] <= 0.35
    assert style["cover_y_ratio"] >= 0.90
    drawbox = bot.subdub_cover_filter(style)
    assert "h=ih*0.24" not in drawbox
    assert "y=ih*0.90" in drawbox or "y=ih*0.91" in drawbox


def test_subtitle_style_bold_outline_readable():
    style = bot.subdub_normalize_style({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "burn", "video_width": 1280, "video_height": 720})
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)
    assert style["size"] >= 44
    assert style["outline"] >= 4
    assert style["shadow"] >= 1
    assert "Style: Default" in ass
    assert ",-1,0,0,0," in ass


def test_vietnamese_font_no_broken_glyph():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "burn"})
    assert "Xin chào thế giới" in ass
    assert "\x00" not in ass
    assert "0 0 0" not in ass


def test_subtitle_only_back_returns_subtitle_setup():
    route = bot.video_dubbing_back_route(
        {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "step": "confirm"},
        "back_confirm",
    )
    assert route == "output"


def test_dub_only_back_returns_dub_setup():
    route = bot.video_dubbing_back_route(
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB, "step": "confirm"},
        "back_confirm",
    )
    assert route == "voice"


def test_combined_back_returns_combined_setup():
    route = bot.video_dubbing_back_route(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "step": "confirm"},
        "back_confirm",
    )
    assert route == "voice"


def test_status_back_button_goes_subdub_menu():
    markup = bot.subdub_progress_keyboard("job1", "vi")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in callbacks
    assert all(callback != "menu|main" or button.text.endswith("Menu chính") for row in markup.inline_keyboard for button in row for callback in [button.callback_data])


def test_missing_origin_fallback_subdub_menu_not_main():
    assert bot.subdub_missing_origin_back_callback() == "videodub|back_type"
    assert bot.subdub_missing_origin_back_callback() != "menu|main"


def test_subdub_delivery_large_video_document_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", 1)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", 4)
    monkeypatch.setattr(bot, "GENERATED_MEDIA_MAX_MB", 4)
    payload = b"\x00\x00\x00\x18ftypmp42" + (b"x" * (2 * 1024 * 1024))
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=payload,
            include_subtitle_outputs=False,
        )
    )
    assert sent["video"] == 0
    assert sent["video_document"] == 1
    assert sent["documents"] == 1
    assert sent["telegram_message_id"]


def test_subdub_pipeline_audit_all_modes_core_enabled():
    payload = bot.subdub_pipeline_audit_payload()
    assert payload["canonical_core_enabled"] is True
    assert payload["subtitle_only_uses_core"] is True
    assert payload["dub_only_uses_core"] is True
    assert payload["subtitle_dub_uses_core"] is True
    assert payload["output_fit_mode"] == "cover"
    assert payload["cover_enabled"] is False


def test_subdub_back_route_audit_ok():
    payload = bot.subdub_back_route_audit_payload()
    assert payload["missing_origin_fallback"] == "videodub|back_type"
    assert payload["missing_origin_count"] == 0
    targets = {item["screen"]: item["back_target"] for item in payload["routes"]}
    assert targets["subtitle_language_confirm"] == "language"
    assert targets["subtitle_only_confirm"] == "output"
    assert targets["dub_only_confirm"] == "voice"
    assert targets["subtitle_dub_confirm"] == "voice"


def test_no_music_video_generation_payos_pricing_changes():
    source = inspect.getsource(bot.subdub_pipeline_audit_payload) + inspect.getsource(bot.subdub_render_style_audit_payload)
    forbidden = ("Suno", "PayOS", "wallet", "topup", "pricing")
    assert all(word not in source for word in forbidden)
