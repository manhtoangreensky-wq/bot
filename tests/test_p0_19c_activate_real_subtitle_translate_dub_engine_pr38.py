import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42toanaas" + b"x" * 4096


class CaptureMessage:
    def __init__(self, chat_id=919900):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})

    async def reply_document(self, **kwargs):
        self.outputs.append({"document": True, **kwargs})

    async def reply_audio(self, **kwargs):
        self.outputs.append({"audio": True, **kwargs})

    async def reply_video(self, **kwargs):
        self.outputs.append({"video": True, **kwargs})


class CaptureQuery:
    def __init__(self, user_id=919900):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _video_state(mode, **extra):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_file_id": "tg-video-p019c",
        "video_file_id": "tg-video-p019c",
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
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: {"internal_job_id": "p019c-job", **payload})
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
            "translation_provider": "",
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
    monkeypatch.setattr(bot, "VIDEO_DUB_MUX_ENABLED", True)
    monkeypatch.setattr(bot, "video_dubbing_video_render_ready", lambda *_args, **_kwargs: True)


def test_p0_19c_combo_menu_keeps_only_canonical_create_translate_dub_path():
    source_labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    no_subtitle_labels = _labels(bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi"))
    assert "🎞 Video đã có phụ đề" in source_labels
    assert "🎧 Video chưa có phụ đề" in source_labels
    assert "🎬 Tạo phụ đề rồi lồng tiếng" in no_subtitle_labels
    assert "🎙 Lồng tiếng trực tiếp" not in no_subtitle_labels
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE}" in _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))


def test_auto_subtitle_calls_real_pipeline_not_admin_test(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)

    async def fake_render(source_bytes, dubbed_audio=b"", subtitle_bytes=b"", **_kwargs):
        calls.append(("render", len(source_bytes), len(dubbed_audio), len(subtitle_bytes)))
        return MP4_BYTES, "subtitle_video"

    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "video_dubbing_video_render_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    query = CaptureQuery()
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            query,
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_CREATE, output_type="burn"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_subtitle"] is True
    assert result["has_video"] is True
    assert any(item[0] == "prepare" for item in calls)
    assert any(item[0] == "render" and item[3] > 0 for item in calls)
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "subtitle_dub_product_pipeline.process_subtitle_dub_job" in core_source
    assert "cmd_tool_test" not in core_source


def test_translate_srt_preserves_timestamps(monkeypatch):
    async def fake_translate(text, target_language, **_kwargs):
        return {"provider": "real_translate_route", "text": f"{text} EN", "target": target_language}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    translated = asyncio.run(bot.translate_subtitle_segments(list(VALID_SEGMENTS), "en", allow_admin=True))

    assert translated["provider"] == "real_translate_route"
    assert "00:00:00,000 --> 00:00:02,000" in translated["srt"]
    assert "Xin chao EN" in translated["srt"]


def test_translate_subtitle_calls_real_pipeline(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)

    async def fake_render(source_bytes, dubbed_audio=b"", subtitle_bytes=b"", **_kwargs):
        calls.append(("render", len(source_bytes), len(dubbed_audio), len(subtitle_bytes)))
        return MP4_BYTES, "translated_subtitle_video"

    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "video_dubbing_video_render_ready", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, output_type="burn", target_language="English"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_subtitle"] is True
    assert result["has_video"] is True
    assert any(item[0] == "prepare" for item in calls)
    assert any(item[0] == "render" and item[3] > 0 for item in calls)


def test_dub_video_calls_real_pipeline(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)

    query = CaptureQuery()
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            query,
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", voice_speed="1.0"),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is True
    assert result["partial_result"] is False
    assert any(item[0] == "tts" for item in calls)
    assert any(item[0] == "render" and item[2] > 0 for item in calls)


def test_subtitle_plus_dub_has_subtitle_calls_real_pipeline(monkeypatch):
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
                voice_style="Nữ mặc định",
                voice_speed="1.0",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_subtitle"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is True
    assert any(item[0] == "prepare" for item in calls)
    assert any(item[0] == "tts" for item in calls)


def test_legacy_no_subtitle_direct_dub_is_canonicalized_before_pipeline(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)

    query = CaptureQuery()
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            query,
            SimpleNamespace(),
            _video_state(
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
                flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
                combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
                output_type="video",
                translate_requested="1",
                target_language="English",
                voice_style="Nữ mặc định",
                voice_speed="1.0",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["partial_result"] is False
    assert result["has_subtitle"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is True
    assert any(item[0] == "render" and item[3] > 0 for item in calls)
    assert any(item.get("video") for item in query.message.outputs)


def test_no_subtitle_create_subtitle_then_dub_calls_real_pipeline(monkeypatch):
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
                voice_style="Nữ mặc định",
                voice_speed="1.0",
            ),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["has_video"] is True
    assert any(item[0] == "prepare" for item in calls)
    assert any(item[0] == "render" and item[3] > 0 for item in calls)


def test_pr38_smoke_commands_still_admin_only():
    source = inspect.getsource(bot)
    for command, handler in {
        "tool_test_asr": "cmd_tool_test_asr",
        "tool_test_auto_subtitle": "cmd_tool_test_subtitle_generate",
        "tool_test_dub_audio": "cmd_tool_test_video_dub",
        "tool_test_full_dub_video": "cmd_tool_test_full_dub_video",
    }.items():
        assert f'CommandHandler("{command}", {handler})' in source
    assert "if not is_admin_user(update.effective_user.id)" in inspect.getsource(bot.cmd_tool_test_full_dub_video)


def test_srt_vtt_txt_support_preserved():
    items = bot.video_dubbing_subtitle_output_items(VALID_SRT, "all", bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert [item["output_type"] for item in items] == ["srt", "vtt", "txt"]
    assert items[0]["bytes"]
    assert items[1]["bytes"].startswith(b"WEBVTT")
    assert b"Xin chao" in items[2]["bytes"]


def test_recent_subtitle_source_preserved_if_available():
    assert callable(bot.video_dubbing_recent_subtitle_source)
    assert "source_recent_subtitle" in inspect.getsource(bot.handle_video_dubbing_callback)


def test_product_failure_no_admin_test_adapter_code_words():
    text = bot.subtitle_plus_dub_clean_failure_text("vi").lower()
    for forbidden in ("admin", "test", "provider", "api", "asr", "tts", "mux", "ffmpeg", "adapter", "adapter_missing", "code", "component", "config", "debug", "traceback"):
        assert forbidden not in text


def test_no_charge_before_valid_subtitle_artifact(monkeypatch):
    charge_calls = []
    _patch_product_core(monkeypatch, admin=False, charge_calls=charge_calls)

    async def failed_job(**_kwargs):
        return {"ok": False, "status": "NO_OUTPUT_BYTES", "error_code": "subtitle_empty"}

    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", failed_job)
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_CREATE, output_type="burn"),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is False
    assert charge_calls == []


def test_no_charge_before_valid_audio_artifact(monkeypatch):
    charge_calls = []
    _patch_product_core(monkeypatch, admin=False, charge_calls=charge_calls)

    async def failed_job(**_kwargs):
        return {"ok": False, "status": "NO_AUDIO_BYTES", "error_code": "dub_audio_empty"}

    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", failed_job)
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định"),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is False
    assert charge_calls == []


def test_no_charge_before_valid_mp4_artifact(monkeypatch):
    calls = []
    charge_calls = []
    _patch_product_core(monkeypatch, admin=False, charge_calls=charge_calls)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=False)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", voice_speed="1.0"),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is True
    assert result["partial_result"] is True
    assert result["has_video"] is False
    assert result["charged"] == 0
    assert charge_calls == []


def test_final_mp4_required_for_video_success():
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
    assert result["result_type"] != "mp4"
    assert result["video_output"] == b""


def test_custom_voice_uses_provider_voice_id_without_touching_voice_core(monkeypatch):
    calls = []
    _patch_product_core(monkeypatch, admin=True)
    _patch_prepare(monkeypatch, calls)
    _patch_dub(monkeypatch, calls, render_video=True)
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice_id", lambda _uid, _state: "provider-voice-id")
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice", lambda _uid, _state: {"ok": True, "provider_voice_id": "provider-voice-id", "tts_payload_voice_id": "provider-voice-id", "resolved_gender": "", "fallback_used": False})

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            SimpleNamespace(),
            _video_state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_kind="custom", voice_style="Voice riêng", voice_speed="1.0"),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is True
    assert ("tts", 1, "provider-voice-id") in calls


def test_admin_diagnostic_contains_private_reason_public_does_not():
    admin_text = bot.admin_product_engine_missing_text("subtitle_plus_dub", {"technical_missing": ["asr_adapter_missing"]})
    public_text = bot.subtitle_plus_dub_clean_failure_text("vi")
    assert "asr_adapter_missing" in admin_text
    assert "asr_adapter_missing" not in public_text
