import asyncio
import inspect
import os
from types import SimpleNamespace

import bot


VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42-live-video"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-final-video" + b"x" * 4096
SRT_TEXT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]


class CaptureMessage:
    def __init__(self, chat_id=919920):
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
    def __init__(self, user_id=919920):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


class FakeTelegramFile:
    async def download_as_bytearray(self):
        return bytearray(VIDEO_BYTES)


class FakeBot:
    async def get_file(self, file_id):
        assert file_id
        return FakeTelegramFile()


def _context():
    return SimpleNamespace(bot=FakeBot())


def _state(mode, **extra):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_file_id": "tg-video-p019e",
        "video_file_id": "tg-video-p019e",
        "source_file_name": "clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": "2",
        "source_duration": "2",
        "target_language": "English",
        **extra,
    }


def _patch_engine_ready(monkeypatch, *, admin=False, access_allowed=False, charge_calls=None):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "get_asr_adapter_readiness", lambda public=True: {"configured": True, "public_ready": True})
    monkeypatch.setattr(bot, "video_translation_provider_configured", lambda: True)
    monkeypatch.setattr(bot, "video_tts_provider_configured_for_dub", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"ok": True, "missing": [], "reason": "ready"})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
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
    else:
        monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: {"ok": True, "final_cost": 150})
    monkeypatch.setattr(bot, "write_media_asset_bytes", lambda kind, asset_id, data, suffix: os.path.join(os.getcwd(), f"{kind}_{asset_id}{suffix}"))
    monkeypatch.setattr(bot, "create_subtitle_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_translation_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_dub_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: {"internal_job_id": "p019e-job", **payload})
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice_id", lambda _uid, _state: "default_voice")
    monkeypatch.setattr(bot, "resolve_video_dub_tts_voice", lambda _uid, _state: {"ok": True, "provider_voice_id": "default_voice", "tts_payload_voice_id": "default_voice", "resolved_gender": "female", "fallback_used": False})
    monkeypatch.setattr(bot, "parse_video_dubbing_voice_speed", lambda _value: 1.0)
    async def fake_validate(_video_bytes, *, require_audio=False, min_bytes=None):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": bool(require_audio), "size": len(_video_bytes or b"")}
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    monkeypatch.setattr(
        bot,
        "video_dubbing_engine_access_decision",
        lambda *_args, **_kwargs: {
            "allowed": bool(access_allowed),
            "status": "allowed_public" if access_allowed else "blocked_public_maintenance",
            "reason": "public_flag" if not access_allowed else "ready",
            "readiness": {
                "configured": True,
                "public_ready": bool(access_allowed),
                "technical_missing": [],
                "public_blockers": [] if access_allowed else ["public_flag"],
                "reason": "public_flag" if not access_allowed else "ready",
            },
        },
    )


def _patch_send(monkeypatch):
    async def fake_send(_message, **kwargs):
        return {
            "documents": 1 if kwargs.get("subtitle_items") else 0,
            "audio": 1 if kwargs.get("audio_bytes") else 0,
            "video": 1 if kwargs.get("video_bytes") else 0,
        }

    monkeypatch.setattr(bot, "send_public_subtitle_dub_final_outputs", fake_send)


def _patch_blackbox(monkeypatch, calls, *, ok=True, video=True, audio=True):
    async def fake_blackbox(**kwargs):
        state = dict(kwargs["state"])
        source_path = str(state.get("_pipeline_saved_source_path") or "")
        calls.append({
            "mode": kwargs["mode"],
            "state": state,
            "source_path": source_path,
            "source_exists": bool(source_path and os.path.exists(source_path)),
        })
        if not ok:
            return {"ok": False, "status": "NO_AUDIO_BYTES", "error_code": "dub_audio_empty", "prepared": {"asr_provider": "asr_live"}}
        return {
            "ok": True,
            "status": "PARTIAL_VIDEO_NOT_READY" if audio and not video else "OK",
            "result_type": "mp4" if video else "partial_audio_subtitle",
            "partial_result": bool(audio and not video),
            "partial_reason": "mux_unavailable" if audio and not video else "",
            "state": state,
            "prepared": {"asr_provider": "asr_live", "translation_provider": "translate_live"},
            "source_bytes": bytes(state.get("_pipeline_source_bytes_override") or VIDEO_BYTES),
            "content_type": "video/mp4",
            "asr_provider": "asr_live",
            "translation_provider": "translate_live",
            "tts_provider": "tts_live" if audio else "",
            "output_subtitle": SRT_TEXT,
            "output_text": "Xin chao",
            "output_segments": list(SEGMENTS),
            "srt_text": SRT_TEXT,
            "srt_bytes": SRT_TEXT.encode("utf-8"),
            "subtitle_items": [{"output_type": "srt", "bytes": SRT_TEXT.encode("utf-8"), "filename": "result.srt", "suffix": ".srt", "caption": ""}],
            "tts_chunks": [{"start": 0, "end": 2, "audio_bytes": b"voice"}] if audio else [],
            "audio_bytes": b"audio-bytes" if audio else b"",
            "video_output": MP4_BYTES if video else b"",
            "normalization_detail": "normalized" if audio else "not_requested",
            "selected_tts_voice_id": "default_voice" if audio else "",
        }

    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", fake_blackbox)


def test_p0_19e_product_upload_does_not_return_before_file_save():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert source.index("video_dubbing_save_input_for_pipeline") < source.index("video_dubbing_engine_access_decision")


def test_p0_19e_input_video_saved_and_exists_before_pipeline(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, access_allowed=True)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            _context(),
            _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert calls and calls[0]["source_exists"] is True
    assert os.path.exists(result["workspace_artifacts"]["source"])


def test_p0_19e_product_route_not_blocked_by_admin_only_guard(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)

    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            _context(),
            _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert calls
    assert result["gate_matrix"]["gate_overridden_for_product"] is True


def test_p0_19e_blackbox_gate_enabled_for_product_when_config_ready(monkeypatch):
    _patch_engine_ready(monkeypatch, access_allowed=False)
    matrix = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, voice_style="Nữ mặc định"),
        access=bot.video_dubbing_engine_access_decision(1, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, {}),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES)},
    )
    assert matrix["blackbox_enabled"] is True
    assert matrix["product_route_allowed"] is True


def test_p0_19e_asr_gate_enabled_for_product_when_config_ready(monkeypatch):
    _patch_engine_ready(monkeypatch, access_allowed=False)
    matrix = bot.video_dubbing_product_gate_matrix(1, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))
    assert matrix["asr_enabled"] is True


def test_p0_19e_tts_gate_enabled_for_product_when_config_ready(monkeypatch):
    _patch_engine_ready(monkeypatch, access_allowed=False)
    matrix = bot.video_dubbing_product_gate_matrix(1, bot.VIDEO_SUBTITLE_MODE_DUB, _state(bot.VIDEO_SUBTITLE_MODE_DUB, voice_style="Nữ mặc định"))
    assert matrix["tts_enabled"] is True


def test_p0_19e_mux_gate_uses_ffmpeg_readiness_not_old_disabled_flag(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_DUB_MUX_ENABLED", False)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    _patch_engine_ready(monkeypatch, access_allowed=True)
    matrix = bot.video_dubbing_product_gate_matrix(1, bot.VIDEO_SUBTITLE_MODE_DUB, _state(bot.VIDEO_SUBTITLE_MODE_DUB))
    assert matrix["ffmpeg_available"] is True
    assert matrix["mux_enabled"] is True


def test_p0_19e_video_has_subtitle_path_attempts_pipeline(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
        output_type="video_subtitle",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )
    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))
    assert result["ok"] is True
    assert calls[0]["mode"] == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB


def test_p0_19e_no_subtitle_direct_dub_attempts_asr_tts_mux(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
        output_type="video",
        translate_requested="1",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )
    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))
    assert result["ok"] is True
    assert result["provider_route"]["asr"] == "asr_live"
    assert result["provider_route"]["tts"] == "tts_live"
    assert result["has_video"] is True


def test_p0_19e_no_subtitle_create_subtitle_then_dub_attempts_asr_translate_tts_mux(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
        output_type="video_subtitle",
        translate_requested="1",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )
    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))
    assert result["ok"] is True
    assert result["provider_route"]["translation"] == "translate_live"
    assert result["provider_route"]["tts"] == "tts_live"
    assert result["has_video"] is True


def test_p0_19e_does_not_show_unprocessed_file_when_pipeline_attempted(monkeypatch, tmp_path):
    calls = []
    charge_calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False, charge_calls=charge_calls)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False)
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            _context(),
            _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is False
    assert result["pipeline_attempted"] is True
    assert result["input_save"]["file_saved"] is True
    assert "chưa xử lý file" not in result["text"].lower()
    assert charge_calls == []


def test_p0_19e_admin_debug_reports_gate_matrix():
    text = bot.subtitle_dub_debug_text({
        "internal_job_id": "SD-E",
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "failed",
        "stage": "gate",
        "pipeline_attempted": False,
        "input_file_id": "tg-file",
        "input_file_path": "/tmp/input.mp4",
        "input_file_exists": True,
        "input_file_size": 10,
        "gate_matrix": {
            "product_route_allowed": True,
            "blackbox_enabled": True,
            "asr_enabled": True,
            "translation_enabled": True,
            "tts_enabled": True,
            "mux_enabled": True,
            "ffmpeg_available": True,
            "provider_gate_reason": "public_flag",
            "technical_missing": [],
            "public_blockers": ["public_flag"],
        },
    })
    assert "gate product route allowed" in text
    assert "gate blackbox enabled" in text
    assert "gate reason" in text


def test_p0_19e_public_failure_clean_no_technical_words():
    text = bot.subtitle_plus_dub_clean_failure_text("vi").lower()
    assert "TOAN AAS chưa xử lý được video này lúc này".lower() in text
    for forbidden in ("admin", "test", "blackbox", "provider", "api", "asr", "tts", "mux", "ffmpeg", "debug", "code", "adapter", "traceback", "payload", "chưa xử lý file"):
        assert forbidden not in text


def test_p0_19e_no_charge_before_artifact(monkeypatch, tmp_path):
    calls = []
    charge_calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False, charge_calls=charge_calls)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False)
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            _context(),
            _state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is False
    assert charge_calls == []


def test_p0_19e_no_fake_success_without_mp4(monkeypatch, tmp_path):
    calls = []
    charge_calls = []
    _patch_engine_ready(monkeypatch, access_allowed=False, charge_calls=charge_calls)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=True, audio=True, video=False)
    result = asyncio.run(
        bot._execute_video_dubbing_pipeline_core(
            CaptureQuery(),
            _context(),
            _state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
            "vi",
            admin_interactive_confirm=True,
        )
    )
    assert result["ok"] is True
    assert result["partial_result"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is False
    assert result["charged"] == 0
    assert charge_calls == []


def test_p0_19e_tool_test_full_dub_video_preserved():
    assert "build_subtitle_dubbed_video_pipeline" in inspect.getsource(bot.cmd_tool_test_full_dub_video)
