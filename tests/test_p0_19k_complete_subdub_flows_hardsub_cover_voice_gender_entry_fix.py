import asyncio
import copy
import inspect

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019k" + b"x" * 4096


def _entry_state(mode, uid=190700):
    bot.clear_video_dubbing_pending(uid)
    return bot.set_video_dubbing_pending(
        uid,
        "source",
        mode=mode,
        process_type=mode,
        video_processing_mode=mode,
        **bot.subdub_entry_state_fields(mode, source_entry=mode, origin="translation"),
    )


def _labels_for_product(product_type):
    return [item["label"] for item in bot.subdub_progress_steps_for_product(product_type)]


async def _run_core(mode, *, output_subtitle=VALID_SRT, output_script="Xin chao", output_segments=None, synth_audio=True, output_type="video"):
    output_segments = VALID_SEGMENTS if output_segments is None else output_segments
    calls = {"subtitle_items": 0, "tts": 0, "render": 0}

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

    async def render_video(*_args, **_kwargs):
        calls["render"] += 1
        return MP4_BYTES, "rendered"

    result = await subtitle_dub_product_pipeline.process_subtitle_dub_job(
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


def test_subtitle_menu_entry_routes_to_subtitle_only_core():
    state = _entry_state(bot.VIDEO_SUBTITLE_MODE_CREATE)

    assert state["product_type"] == "subtitle_only"
    assert state["expected_media"] == "video"
    assert state["source_entry"] == bot.VIDEO_SUBTITLE_MODE_CREATE
    assert "videodub|type|subtitle_create" in state["back_stack"]


def test_dub_menu_entry_routes_to_dub_only_core():
    state = _entry_state(bot.VIDEO_SUBTITLE_MODE_DUB)

    assert state["product_type"] == "dub_only"
    assert state["expected_media"] == "video"
    assert state["active_flow"] == "dub_audio"


def test_subtitle_dub_menu_entry_routes_to_combined_core():
    state = _entry_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    assert state["product_type"] == "subtitle_dub"
    assert state["expected_media"] == "video"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB


def test_no_subdub_public_entry_raises_generic_error():
    text = " ".join(
        bot.video_dubbing_flow_failure_text(mode, "vi")
        for mode in (
            bot.VIDEO_SUBTITLE_MODE_CREATE,
            bot.VIDEO_SUBTITLE_MODE_DUB,
            bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        )
    )

    assert "Có lỗi khi xử lý lệnh" not in text
    assert not any(word in text.lower() for word in ("provider", "api", "ffmpeg", "mux", "asr", "tts"))


def test_subdub_panel_buttons_route_to_same_core():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    callbacks = [
        button.callback_data
        for row in bot.subdub_progress_keyboard("job-p019k", "vi").inline_keyboard
        for button in row
    ]

    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "videodub|subdub_status|job-p019k" in callbacks
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in callbacks


def test_subtitle_only_accepts_video_and_advances():
    state = _entry_state(bot.VIDEO_SUBTITLE_MODE_CREATE)
    steps = _labels_for_product(state["product_type"])

    assert "Nhận video" in steps
    assert "Ghép phụ đề" in steps
    assert "Tạo giọng lồng tiếng" not in steps


def test_subtitle_only_does_not_require_dub_audio():
    result, calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_CREATE, synth_audio=False, output_type="burn"))

    assert result["ok"] is True
    assert result["product_type"] == "subtitle_only"
    assert result["srt_bytes"]
    assert result["audio_bytes"] == b""
    assert calls["tts"] == 0


def test_subtitle_only_success_requires_subtitle_artifact():
    result, _calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_CREATE, output_subtitle="", output_script="", output_segments=[], output_type="burn"))

    assert result["ok"] is False
    assert result["status"] == "SUBTITLE_EMPTY"
    assert result["charged"] is False


def test_subtitle_only_clean_fail_no_charge():
    text = bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_CREATE, "vi")

    assert "chưa trừ Xu" in text
    assert "provider" not in text.lower()


def test_dub_only_requires_tts_audio_before_success():
    result, _calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_DUB, synth_audio=False, output_type="video"))

    assert result["ok"] is False
    assert result["status"] == "NO_AUDIO_BYTES"
    assert result["charged"] is False


def test_dub_only_respects_selected_male_voice(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_male", "voice_style": "Giọng nam"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == "male-real-voice"
    assert state["selected_voice_gender"] == "male"
    assert state["resolved_gender"] == "male"


def test_dub_only_respects_selected_female_voice(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == "female-real-voice"
    assert state["selected_voice_gender"] == "female"
    assert state["resolved_gender"] == "female"


def test_dub_only_no_silent_gender_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_ALLOW_SILENT_VOICE_FALLBACK", False)
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == ""
    assert state["_subdub_voice_resolution"]["ok"] is False
    assert state["_subdub_voice_resolution"]["fallback_used"] is False


def test_dub_only_output_requires_audio_stream(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": False, "size": 4096}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    validation = asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=True, min_bytes=16))

    assert validation["ok"] is False
    assert validation["detail"] == "audio_stream_missing"


def test_subtitle_dub_requires_subtitle_and_dub_audio():
    no_subtitle, _calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_subtitle="", output_script="", output_segments=[]))
    no_audio, _calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, synth_audio=False))

    assert no_subtitle["ok"] is False
    assert no_subtitle["status"] == "SUBTITLE_EMPTY"
    assert no_audio["ok"] is False
    assert no_audio["status"] == "NO_AUDIO_BYTES"


def test_subtitle_dub_success_once():
    key = "p019k-success-once"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)

    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="m1") is True
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="m2") is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["subdub_success_message_id"] == "m1"


def test_subtitle_dub_no_fail_then_success():
    key = "p019k-no-late-success"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)
    bot.update_subtitle_dub_pipeline_job(key, status="failed", terminal_state="failed_no_charge")

    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == "failed_no_charge"


def test_translated_subtitle_output_enables_hardsub_cover_by_default(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_HARDSUB_COVER_ENABLED", True)
    state = bot.subdub_output_style_state(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "translate_requested": "1", "output_type": "burn"},
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    )

    assert state["hardsub_cover_enabled"] is True
    assert state["subtitle_style_preset"] == "cover_original"


def test_hardsub_cover_drawbox_or_ass_style_present(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_HARDSUB_COVER_Y_RATIO", 0.76)
    monkeypatch.setattr(bot, "SUBDUB_HARDSUB_COVER_HEIGHT_RATIO", 0.18)
    style = bot.subdub_output_style_state(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "output_type": "video_subtitle",
            "hardsub_cover_enabled": "1",
        },
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )
    filter_text = bot.subdub_cover_filter(style)
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)

    assert filter_text == "" or "drawbox=" in filter_text
    assert ",3," in ass
    assert "Dialogue: 0" in ass


def test_hardsub_cover_has_opacity_config(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_HARDSUB_COVER_OPACITY", 0.60)
    style = bot.subdub_normalize_style(
        bot.subdub_output_style_state(
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "translate_requested": "1", "hardsub_cover_enabled": "1"},
            bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        )
    )

    assert style["cover_opacity"] == 0.35


def test_subtitle_render_places_translated_text_over_cover():
    state = bot.subdub_output_style_state(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "translate_requested": "1", "hardsub_cover_enabled": "1"},
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    )
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, state)

    assert "Style: Default" in ass
    assert "Xin chao" in ass
    assert bot.subdub_cover_filter(state).startswith("drawbox=") or ",3," in ass


def test_dub_only_does_not_force_cover_unless_requested():
    default_state = bot.subdub_output_style_state({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "output_type": "video"}, bot.VIDEO_SUBTITLE_MODE_DUB)
    requested_state = bot.subdub_output_style_state({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "output_type": "video", "hardsub_cover_enabled": "1"}, bot.VIDEO_SUBTITLE_MODE_DUB)

    assert default_state["hardsub_cover_enabled"] is False
    assert requested_state["hardsub_cover_enabled"] is True


def test_subdub_voice_debug_read_only():
    job = {"internal_job_id": "voice-job", "selected_voice_gender": "female", "resolved_gender": "female", "audio_bytes": 123}
    before = copy.deepcopy(job)

    text = bot.subdub_voice_debug_text(job)

    assert job == before
    assert "SUBDUB VOICE DEBUG" in text


def test_subdub_voice_debug_shows_selected_and_resolved_gender():
    text = bot.subdub_voice_debug_text({
        "internal_job_id": "voice-job",
        "selected_voice_gender": "female",
        "selected_voice_id": "default_female",
        "resolved_voice_id": "female-real-voice",
        "resolved_gender": "female",
    })

    assert "selected_voice_gender" in text
    assert "resolved_gender" in text
    assert "female-real-voice" in text


def test_subdub_voice_debug_shows_fallback_reason_when_unknown():
    text = bot.subdub_voice_debug_text({
        "internal_job_id": "voice-job",
        "selected_voice_gender": "",
        "resolved_gender": "female",
        "auto_detected_gender": "female",
        "fallback_reason": "auto_gender_unknown_default_female",
    })

    assert "fallback_reason" in text
    assert "auto_gender_unknown_default_female" in text


def test_zero_duration_output_not_delivered(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 0.0, "has_video": True, "has_audio": True, "size": 4096}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    assert asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=True, min_bytes=16))["ok"] is False


def test_missing_output_not_success():
    validation = asyncio.run(bot.subdub_validate_video_output(b"", require_audio=False, min_bytes=16))

    assert validation["ok"] is False
    assert validation["detail"] == "video_too_small"


def test_output_no_audio_blocks_dub_success(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": False, "size": 4096}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    assert asyncio.run(bot.subdub_validate_video_output(MP4_BYTES, require_audio=True, min_bytes=16))["detail"] == "audio_stream_missing"


def test_empty_subtitle_blocks_subtitle_success():
    result, _calls = asyncio.run(_run_core(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, output_subtitle="", output_script="", output_segments=[], output_type="burn"))

    assert result["ok"] is False
    assert result["error_code"] == "subtitle_empty"


def test_failed_terminal_blocks_late_success():
    assert bot.subdub_terminal_state_allows_transition("failed_no_charge", "delivered") is False


def test_delivered_terminal_blocks_late_error():
    assert bot.subdub_terminal_state_allows_transition("delivered", "failed_no_charge") is False


def test_subdub_delivery_once():
    key = "p019k-delivery-once"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)

    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is True
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is False


def test_subdub_success_once():
    test_subtitle_dub_success_once()


def test_update_status_does_not_reprocess():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    branch = source[source.find('if action == "subdub_status"'):source.find('if action == "admin_status"')]

    assert "subdub_job_public_status_text" in branch
    assert "execute_video_dubbing_pipeline" not in branch


def test_debug_does_not_send_file():
    source = "\n".join(inspect.getsource(func) for func in (
        bot.cmd_subdub_job_debug,
        bot.cmd_subdub_render_debug,
        bot.cmd_subdub_delivery_debug,
        bot.cmd_subdub_voice_debug,
    ))

    assert "reply_video" not in source
    assert "reply_document" not in source
    assert "send_public_subtitle_dub_final_outputs" not in source


def test_subtitle_only_progress_steps_do_not_show_voice_required():
    labels = _labels_for_product("subtitle_only")

    assert "Tạo giọng lồng tiếng" not in labels
    assert "Ghép phụ đề" in labels


def test_dub_only_progress_steps_include_voice():
    labels = _labels_for_product("dub_only")

    assert "Chọn giọng lồng tiếng" in labels
    assert "Tạo giọng lồng tiếng" in labels
    assert "Tạo phụ đề" not in labels


def test_combined_progress_steps_include_subtitle_and_voice():
    labels = _labels_for_product("subtitle_dub")

    assert "Tạo giọng lồng tiếng" in labels
    assert "Dịch nội dung" in labels
    assert any(label in labels for label in ("Dịch nội dung", "Tạo phụ đề"))
