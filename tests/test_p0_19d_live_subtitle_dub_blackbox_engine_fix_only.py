import asyncio
import inspect
import os
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42toanaas" + b"x" * 4096


class CaptureMessage:
    def __init__(self, chat_id=919910):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_document(self, **kwargs):
        self.outputs.append({"document": True, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_audio(self, **kwargs):
        self.outputs.append({"audio": True, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))

    async def reply_video(self, **kwargs):
        self.outputs.append({"video": True, **kwargs})
        return SimpleNamespace(message_id=len(self.outputs))


class CaptureQuery:
    def __init__(self, user_id=919910):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _video_state(mode, **extra):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_file_id": "tg-video-p019d",
        "video_file_id": "tg-video-p019d",
        "source_file_name": "clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": "2",
        "source_duration": "2",
        "_pipeline_source_bytes_override": b"video-bytes",
        **extra,
    }


def _patch_product_core(monkeypatch, *, admin=True, charge_calls=None):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "calculate_video_translate_price", lambda *_args, **_kwargs: {"total_price_xu": 100})
    monkeypatch.setattr(bot, "video_dubbing_tts_price_estimate", lambda *_args, **_kwargs: {"price_xu": 50})
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (999999, 0, 0))
    if charge_calls is not None:
        monkeypatch.setattr(
            bot,
            "spend_fixed_credit_info",
            lambda *_args, **_kwargs: charge_calls.append(_args) or {"ok": True, "final_cost": 150},
        )
    monkeypatch.setattr(bot, "write_media_asset_bytes", lambda kind, asset_id, data, suffix: f"/tmp/{kind}_{asset_id}{suffix}")
    monkeypatch.setattr(bot, "create_subtitle_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_translation_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_dub_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: {"internal_job_id": "p019d-job", **payload})
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice_id", lambda _uid, _state: "default_voice")
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice", lambda _uid, _state: {"ok": True, "provider_voice_id": "default_voice", "tts_payload_voice_id": "default_voice", "resolved_gender": "female", "fallback_used": False})
    monkeypatch.setattr(bot, "parse_video_dubbing_voice_speed", lambda _value: 1.0)
    async def fake_validate(_video_bytes, *, require_audio=False, min_bytes=None):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": bool(require_audio), "size": len(_video_bytes or b"")}
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)


def _patch_prepare(monkeypatch, calls):
    async def fake_prepare(_context, service_state, _uid, allow_admin=False):
        calls.append(("prepare", service_state.get("video_processing_mode"), allow_admin))
        return {
            "state": dict(service_state),
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "source_subtitle": VALID_SRT,
            "source_segments": list(VALID_SEGMENTS),
            "source_script": "Xin chao",
            "output_subtitle": VALID_SRT,
            "output_segments": list(VALID_SEGMENTS),
            "output_script": "Xin chao",
            "asr_provider": "real_asr_route",
            "translation_provider": "real_translate_route" if service_state.get("target_language") else "",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)


def _patch_dub(monkeypatch, calls, *, render_video=True):
    async def fake_synthesize(segments, **kwargs):
        calls.append(("tts", len(segments), kwargs.get("voice_id")))
        return {"provider": "real_tts_route", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"audio", "audio_duration": 2.0}]}

    async def fake_timeline(chunks, total_duration=0):
        calls.append(("timeline", len(chunks), total_duration))
        return b"timeline-audio", "timeline"

    async def fake_normalize(audio_bytes):
        calls.append(("normalize", len(audio_bytes)))
        return b"normalized-audio", "normalized"

    async def fake_render(source_bytes, dubbed_audio=b"", subtitle_bytes=b"", **_kwargs):
        calls.append(("render", len(source_bytes), len(dubbed_audio), len(subtitle_bytes)))
        return (MP4_BYTES if render_video else b""), ("rendered" if render_video else "mux_failed")

    monkeypatch.setattr(bot, "synthesize_dub_segment_chunks", fake_synthesize)
    monkeypatch.setattr(bot, "build_dub_timeline_audio", fake_timeline)
    monkeypatch.setattr(bot, "normalize_dub_audio_bytes", fake_normalize)
    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")


def test_p0_19d_public_entry_single_lane_keeps_legacy_no_subtitle_menu():
    source_callbacks = _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    no_subtitle_labels = _labels(bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi"))
    assert source_callbacks.count("videodub|source_upload") == 1
    assert not any(callback.startswith("videodub|path|") for callback in source_callbacks)
    assert "🎬 Tạo phụ đề rồi lồng tiếng" in no_subtitle_labels
    assert "🎙 Lồng tiếng trực tiếp" not in no_subtitle_labels


def test_live_no_subtitle_direct_dub_calls_blackbox_full_dub(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
                output_type="video",
                translate_requested="1",
                target_language="English",
                voice_style="Nu mac dinh",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is True
    assert result["partial_result"] is False
    assert [item[0] for item in calls] == ["prepare", "tts", "timeline", "normalize", "render"]


def test_live_no_subtitle_create_subtitle_then_dub_calls_blackbox(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
                output_type="video_subtitle",
                translate_requested="1",
                target_language="English",
                voice_style="Nu mac dinh",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_video"] is True
    assert any(item[0] == "render" and item[3] > 0 for item in calls)


def test_has_subtitle_subtitle_plus_dub_calls_blackbox(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
                output_type="video_subtitle",
                translate_requested="1",
                target_language="English",
                voice_style="Nu mac dinh",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_video"] is True
    assert any(item[0] == "prepare" for item in calls)
    assert any(item[0] == "tts" for item in calls)
    assert any(item[0] == "render" for item in calls)


def test_auto_subtitle_produces_real_srt_artifact(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_CREATE, output_type="srt"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_subtitle"] is True
    assert result["has_audio"] is False
    assert any(item.get("document") for item in result["state"].get("_unused_outputs", []) or []) is False


def test_translate_subtitle_preserves_srt_timestamps(monkeypatch):
    async def fake_translate(text, target_language, **_kwargs):
        return {"provider": "real_translate_route", "text": f"{text} EN", "target": target_language}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    translated = asyncio.run(bot.translate_subtitle_segments(list(VALID_SEGMENTS), "en", allow_admin=True))

    assert translated["provider"] == "real_translate_route"
    assert "00:00:00,000 --> 00:00:02,000" in translated["srt"]
    assert "Xin chao EN" in translated["srt"]


def test_dub_video_requires_audio_artifact():
    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao",
            "output_segments": list(VALID_SEGMENTS),
            "asr_provider": "real_asr_route",
        }

    async def empty_tts(*_args, **_kwargs):
        return {"provider": "real_tts_route", "chunks": []}

    async def empty_timeline(*_args, **_kwargs):
        return b"", "empty"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"output_type": "video", "video_duration": "2"},
            user_id=1,
            prepare_subtitles=prepare_subtitles,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda _uid, _state: "voice",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=empty_tts,
            build_timeline_audio=empty_timeline,
            normalize_audio=lambda audio: (bytes(audio), "normalized"),
            render_video=lambda *_args, **_kwargs: (MP4_BYTES, "rendered"),
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "NO_AUDIO_BYTES"
    assert result["charged"] is False


def test_full_dub_requires_mp4_for_video_success(monkeypatch):
    calls = []
    charge_calls = []
    _patch_product_core(monkeypatch, admin=False, charge_calls=charge_calls)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=False)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nu mac dinh"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is False
    assert result.get("has_video") is not True
    assert result.get("charged", 0) == 0
    assert charge_calls == []


def test_mux_failure_is_partial_not_final_success():
    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao",
            "output_segments": list(VALID_SEGMENTS),
            "asr_provider": "real_asr_route",
        }

    async def synthesize_segments(*_args, **_kwargs):
        return {"provider": "real_tts_route", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"audio", "audio_duration": 2}]}

    async def build_timeline_audio(*_args, **_kwargs):
        return b"audio", "timeline"

    async def normalize_audio(audio_bytes):
        return bytes(audio_bytes), "normalized"

    async def render_video(*_args, **_kwargs):
        return b"", "mux_failed"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"output_type": "video", "video_duration": "2"},
            user_id=1,
            prepare_subtitles=prepare_subtitles,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda _uid, _state: "voice",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=synthesize_segments,
            build_timeline_audio=build_timeline_audio,
            normalize_audio=normalize_audio,
            render_video=render_video,
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["partial_result"] is True
    assert result["result_type"] == "partial_audio_subtitle"
    assert result["video_output"] == b""


def test_product_public_failure_no_blackbox_provider_asr_tts_mux_words():
    text = bot.subtitle_plus_dub_clean_failure_text("vi").lower()
    for forbidden in ("admin", "test", "blackbox", "provider", "api", "asr", "tts", "mux", "ffmpeg", "debug", "code", "adapter", "traceback", "payload"):
        assert forbidden not in text


def test_admin_debug_contains_blackbox_stage_reason():
    text = bot.subtitle_dub_debug_text({
        "internal_job_id": "SD-1",
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "partial",
        "input_file_path": "/tmp/input.mp4",
        "input_file_exists": True,
        "input_file_size": 123,
        "duration_seconds": 2,
        "asr_route_called": True,
        "transcript_length": 8,
        "original_srt_path": "/tmp/original.srt",
        "translated_srt_path": "/tmp/translated.srt",
        "tts_route_called": True,
        "dubbed_audio_path": "/tmp/dub.mp3",
        "dubbed_audio_exists": True,
        "mux_render_called": True,
        "final_mp4_path": "",
        "final_mp4_exists": False,
        "final_mp4_size": 0,
        "last_technical_error": "mux_failed",
        "public_safe_error": "TOAN AAS chưa xử lý file và chưa trừ Xu.",
        "provider_route": {"asr": "real_asr_route", "translation": "real_translate_route", "tts": "real_tts_route", "mux": "skipped_or_not_requested"},
    })

    assert "ASR route called" in text
    assert "TTS route called" in text
    assert "mux/render route called" in text
    assert "final MP4 exists" in text
    assert "mux_failed" in text


def test_no_charge_without_final_mp4_for_video_flow(monkeypatch):
    calls = []
    charge_calls = []
    _patch_product_core(monkeypatch, admin=False, charge_calls=charge_calls)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=False)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nu mac dinh"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is False
    assert result.get("has_video") is not True
    assert result.get("charged", 0) == 0
    assert charge_calls == []


def test_no_fake_success_without_artifact():
    async def prepare_subtitles(state):
        return {"state": dict(state), "source_bytes": b"", "content_type": "video/mp4", "output_subtitle": "", "output_script": "", "output_segments": []}

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            state={"output_type": "srt", "video_duration": "2"},
            user_id=1,
            prepare_subtitles=prepare_subtitles,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda _uid, _state: "voice",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=lambda *_args, **_kwargs: {"chunks": []},
            build_timeline_audio=lambda *_args, **_kwargs: (b"", "empty"),
            normalize_audio=lambda audio: (bytes(audio), "normalized"),
            render_video=lambda *_args, **_kwargs: (b"", "none"),
            video_render_ready=lambda _output_type: False,
            ffmpeg_ready=lambda: False,
            dub_mux_enabled=False,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "SUBTITLE_EMPTY"


def test_uploaded_video_file_saved_before_processing(monkeypatch, tmp_path):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_CREATE, output_type="srt", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    source_path = result["workspace_artifacts"]["source"]
    assert source_path
    assert os.path.exists(source_path)
    assert os.path.getsize(source_path) > 0


def test_input_video_extract_audio_called(monkeypatch):
    calls = []

    async def fake_extract(source_bytes, content_type, max_seconds=0):
        calls.append(("extract", len(source_bytes), content_type, max_seconds))
        return b"audio", "audio/mpeg", "extract"

    async def fake_asr(audio_bytes, content_type, **_kwargs):
        calls.append(("asr", len(audio_bytes), content_type))
        return {"provider": "real_asr_route", "text": "Xin chao", "segments": list(VALID_SEGMENTS), "duration_seconds": 2}

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"video", "content_type": "video/mp4", "media_kind": "video", "duration_seconds": 2},
            context=SimpleNamespace(),
            allow_admin=True,
        )
    )

    assert result["output_valid"] is True
    assert calls[0][0] == "extract"
    assert calls[1][0] == "asr"


def test_transcript_non_empty_required(monkeypatch):
    async def empty_asr(*_args, **_kwargs):
        return {"provider": "real_asr_route", "text": "", "segments": [], "detail": "empty"}

    monkeypatch.setattr(bot, "asr_transcribe_audio", empty_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"audio", "content_type": "audio/mpeg", "media_kind": "audio", "duration_seconds": 2},
            context=SimpleNamespace(),
            allow_admin=True,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == "empty_transcript"


def test_tts_audio_non_empty_required():
    return test_dub_video_requires_audio_artifact()


def test_final_mp4_non_empty_required():
    return test_mux_failure_is_partial_not_final_success()


def test_tool_test_full_dub_video_admin_only():
    assert "if not is_admin_user(update.effective_user.id)" in inspect.getsource(bot.cmd_tool_test_full_dub_video)


def test_pr38_smoke_commands_preserved():
    source = inspect.getsource(bot)
    for command in ("tool_test_asr", "tool_test_auto_subtitle", "tool_test_dub_audio", "tool_test_full_dub_video"):
        assert f'CommandHandler("{command}"' in source
    assert "build_subtitle_dubbed_video_pipeline" in inspect.getsource(bot.cmd_tool_test_full_dub_video)


def test_engine_mux_ready_uses_ffmpeg_not_legacy_flag(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_DUB_MUX_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_BURN_IN_ENABLED", False)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    assert bot.video_dubbing_mux_ready() is True
    assert bot.video_dubbing_subtitle_render_ready() is True
    assert bot.video_dubbing_video_render_ready("video", audio=True) is True
    assert bot.video_dubbing_video_render_ready("video_subtitle", subtitle=True) is True
