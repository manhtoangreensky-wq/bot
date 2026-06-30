import asyncio
import inspect
import os
from types import SimpleNamespace

import bot


VIDEO_BYTES = b"\x00\x00\x00\x18ftypmp42-p019f-video"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019f-final" + b"x" * 4096
SRT_TEXT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]


class CaptureMessage:
    def __init__(self, chat_id=919930):
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
    def __init__(self, user_id=919930):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)


class FakeTelegramFile:
    async def download_as_bytearray(self):
        return bytearray(VIDEO_BYTES)


class FakeBot:
    async def get_file(self, file_id):
        assert file_id
        return FakeTelegramFile()


def _context(fake_bot=None):
    return SimpleNamespace(bot=fake_bot or FakeBot())


def _state(mode, **extra):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "source_file_id": "tg-video-p019f",
        "video_file_id": "tg-video-p019f",
        "source_file_name": "clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": "2",
        "source_duration": "2",
        "target_language": "English",
        **extra,
    }


def _patch_engine_ready(
    monkeypatch,
    tmp_path,
    *,
    admin=False,
    access_allowed=False,
    asr=True,
    translate=True,
    tts=True,
    ffmpeg_path="ffmpeg",
    charge_calls=None,
    saved_jobs=None,
):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "get_asr_adapter_readiness", lambda public=True: {"configured": bool(asr), "public_ready": bool(asr)})
    monkeypatch.setattr(bot, "video_translation_provider_configured", lambda: bool(translate))
    monkeypatch.setattr(bot, "video_tts_provider_configured_for_dub", lambda: bool(tts))
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"ok": True, "missing": [], "reason": "ready"})
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: ffmpeg_path)
    monkeypatch.setattr(bot, "calculate_video_translate_price", lambda *_args, **_kwargs: {"total_price_xu": 100})
    monkeypatch.setattr(bot, "video_dubbing_tts_price_estimate", lambda *_args, **_kwargs: {"price_xu": 50})
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (999999, 0, 0))
    if charge_calls is not None:
        monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **_kwargs: charge_calls.append(args) or {"ok": True, "final_cost": 150})
    else:
        monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: {"ok": True, "final_cost": 150})

    def fake_write_asset(kind, asset_id, data, suffix):
        path = os.path.join(str(tmp_path), f"{kind}_{asset_id}{suffix}")
        with open(path, "wb") as handle:
            handle.write(bytes(data or b""))
        return path

    def fake_save_engine_async_job(payload):
        payload = dict(payload or {})
        payload.setdefault("internal_job_id", f"p019f-job-{len(saved_jobs or []) + 1}")
        if saved_jobs is not None:
            saved_jobs.append(payload)
        return payload

    monkeypatch.setattr(bot, "write_media_asset_bytes", fake_write_asset)
    monkeypatch.setattr(bot, "create_subtitle_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_translation_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_dub_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save_engine_async_job)
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
            "reason": "ready" if access_allowed else "public_flag",
            "readiness": {
                "configured": True,
                "public_ready": bool(access_allowed),
                "technical_missing": [],
                "public_blockers": [] if access_allowed else ["public_flag"],
                "reason": "ready" if access_allowed else "public_flag",
            },
        },
    )


def _patch_send(monkeypatch, *, empty=False):
    async def fake_send(_message, **kwargs):
        if empty:
            return {"documents": 0, "audio": 0, "video": 0}
        return {
            "documents": 1 if kwargs.get("subtitle_items") else 0,
            "audio": 1 if kwargs.get("audio_bytes") else 0,
            "video": 1 if kwargs.get("video_bytes") else 0,
        }

    monkeypatch.setattr(bot, "send_public_subtitle_dub_final_outputs", fake_send)


def _patch_blackbox(
    monkeypatch,
    calls,
    *,
    ok=True,
    video=True,
    audio=True,
    status="NO_AUDIO_BYTES",
    error_code="dub_audio_empty",
    admin_debug_summary="dub_audio_empty",
    route_attempts=None,
):
    async def fake_blackbox(**kwargs):
        state = dict(kwargs["state"])
        source_path = str(state.get("_pipeline_saved_source_path") or "")
        attempts = dict(route_attempts or {
            "subtitle_prepare": True,
            "asr": True,
            "translation": True,
            "tts": bool(audio or kwargs["mode"] in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}),
            "mux": bool(video),
            "transcript_length": 8,
        })
        calls.append({
            "mode": kwargs["mode"],
            "state": state,
            "source_path": source_path,
            "source_exists": bool(source_path and os.path.exists(source_path)),
            "route_attempts": attempts,
        })
        if not ok:
            return {
                "ok": False,
                "status": status,
                "error_code": error_code,
                "admin_debug_summary": admin_debug_summary,
                "prepared": {"asr_provider": "asr_live", "translation_provider": "translate_live"},
                "route_attempts": attempts,
            }
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
            "route_attempts": attempts,
        }

    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", fake_blackbox)


def test_product_upload_captures_telegram_file_id(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=True)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    assert result["input_save"]["file_id"] == "tg-video-p019f"


def test_product_upload_saves_local_input_file_before_gate(tmp_path):
    result = asyncio.run(bot.video_dubbing_save_input_for_pipeline(
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        str(tmp_path),
    ))

    assert result["ok"] is True
    assert result["file_saved"] is True
    assert result["exists"] is True
    assert result["path"]
    assert os.path.exists(result["path"])
    assert result["size"] == len(VIDEO_BYTES)


def test_input_path_passed_to_subtitle_dub_pipeline(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=True)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    assert calls[0]["source_path"] == result["workspace_artifacts"]["source"]
    assert calls[0]["source_exists"] is True


def test_product_route_allowed_for_confirmed_subtitle_plus_dub_session(monkeypatch, tmp_path):
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    matrix = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, voice_style="Nữ mặc định"),
        access=bot.video_dubbing_engine_access_decision(1, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, {}),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES), "path": str(tmp_path / "clip.mp4")},
    )

    assert matrix["product_route_allowed"] is True
    assert matrix["blackbox_enabled"] is True
    assert matrix["gate_overridden_for_product"] is True


def test_old_admin_only_gate_does_not_block_product_flow(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    assert calls
    assert result["gate_matrix"]["gate_overridden_for_product"] is True


def test_blackbox_gate_uses_real_readiness_not_default_false(monkeypatch, tmp_path):
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, tts=True)
    ready = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, voice_style="Nữ mặc định"),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES), "path": str(tmp_path / "clip.mp4")},
    )
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, tts=False)
    missing = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, voice_style="Nữ mặc định"),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES), "path": str(tmp_path / "clip.mp4")},
    )

    assert ready["blackbox_enabled"] is True
    assert missing["blackbox_enabled"] is False
    assert "tts" in missing["technical_missing"]


def test_ffmpeg_readiness_uses_actual_binary(monkeypatch, tmp_path):
    _patch_engine_ready(monkeypatch, tmp_path, ffmpeg_path="")
    missing = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_DUB, voice_style="Nữ mặc định"),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES), "path": str(tmp_path / "clip.mp4")},
    )
    _patch_engine_ready(monkeypatch, tmp_path, ffmpeg_path="ffmpeg")
    ready = bot.video_dubbing_product_gate_matrix(
        1,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        _state(bot.VIDEO_SUBTITLE_MODE_DUB, voice_style="Nữ mặc định"),
        input_save={"file_saved": True, "exists": True, "size": len(VIDEO_BYTES), "path": str(tmp_path / "clip.mp4")},
    )

    assert missing["ffmpeg_available"] is False
    assert missing["mux_enabled"] is False
    assert "ffmpeg" in missing["technical_missing"]
    assert ready["ffmpeg_available"] is True
    assert ready["mux_enabled"] is True


def test_pipeline_attempted_after_successful_file_save(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is False
    assert result["input_save"]["file_saved"] is True
    assert result["pipeline_attempted"] is True
    assert result["debug_job"]["pipeline_attempted"] is True
    assert calls


def test_pipeline_attempted_cannot_be_no_when_input_exists_and_gate_ready(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))
    debug_text = bot.subtitle_dub_debug_text(result["debug_job"])

    assert result["debug_job"]["input_file_path"]
    assert "pipeline attempted: <code>yes</code>" in debug_text
    assert "input file path: <code>-</code>" not in debug_text


def test_completed_status_requires_valid_artifact_or_partial_artifact(monkeypatch, tmp_path):
    calls = []
    saved_jobs = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=True, saved_jobs=saved_jobs)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, video=True, audio=True)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    assert result["has_video"] is True
    assert saved_jobs[-1]["status"] == "completed"
    assert saved_jobs[-1]["final_mp4_exists"] is True
    assert saved_jobs[-1]["final_mp4_size"] > 0


def test_no_completed_status_when_pipeline_not_attempted(tmp_path):
    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        SimpleNamespace(bot=SimpleNamespace()),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is False
    assert result["debug_job"]["pipeline_attempted"] is False
    assert result["debug_job"]["status"] != "completed"
    assert result["debug_job"]["pipeline_blocker"] in {"telegram_download_failed", "file_not_saved"}


def test_video_has_subtitle_path_attempts_extract_or_asr(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE,
        output_type="video_subtitle",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))

    assert result["ok"] is True
    assert calls[0]["route_attempts"]["subtitle_prepare"] is True
    assert result["provider_route"]["asr"] in {"asr_live", "cached_subtitle", "embedded_subtitle", "subtitle_file"}


def test_no_subtitle_direct_dub_attempts_asr_translation_tts_mux(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
        output_type="video",
        translate_requested="1",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))

    assert result["ok"] is True
    assert calls[0]["route_attempts"]["asr"] is True
    assert result["provider_route"]["translation"] == "translate_live"
    assert result["provider_route"]["tts"] == "tts_live"
    assert result["has_video"] is True


def test_no_subtitle_create_subtitle_then_dub_attempts_asr_translation_tts_mux(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls)
    state = _state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        combo_subpath=bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
        output_type="video_subtitle",
        translate_requested="1",
        voice_style="Nữ mặc định",
        _pipeline_workspace=str(tmp_path),
    )

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(CaptureQuery(), _context(), state, "vi", admin_interactive_confirm=True))

    assert result["ok"] is True
    assert calls[0]["route_attempts"]["asr"] is True
    assert result["provider_route"]["translation"] == "translate_live"
    assert result["provider_route"]["tts"] == "tts_live"
    assert result["has_video"] is True


def test_admin_debug_reports_real_gate_matrix(tmp_path):
    text = bot.subtitle_dub_debug_text({
        "internal_job_id": "SD-F",
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "failed",
        "stage": "pipeline",
        "pipeline_attempted": True,
        "input_file_id": "tg-file",
        "input_file_path": str(tmp_path / "input.mp4"),
        "input_file_exists": True,
        "input_file_size": 10,
        "pipeline_blocker": "provider_key_missing",
        "gate_matrix": {
            "product_route_allowed": True,
            "blackbox_enabled": False,
            "asr_enabled": True,
            "translation_enabled": True,
            "tts_enabled": False,
            "mux_enabled": True,
            "ffmpeg_available": True,
            "ffmpeg_path": "ffmpeg",
            "provider_gate_reason": "public_flag",
            "gate_blockers": ["provider_key_missing"],
            "technical_missing": ["tts"],
            "public_blockers": ["public_flag"],
        },
    })

    assert "gate product route allowed: <code>yes</code>" in text
    assert "ffmpeg path: <code>ffmpeg</code>" in text
    assert "gate blockers: <code>provider_key_missing</code>" in text
    assert "pipeline blocker: <code>provider_key_missing</code>" in text


def test_admin_debug_reports_file_not_saved_blocker(tmp_path):
    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=1,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state=_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        status="INPUT_SAVE_FAILED",
        stage="input_save",
        input_save={"file_id": "tg-file", "file_saved": False, "exists": False, "size": 0, "path": ""},
        gate_matrix={"product_route_allowed": False, "gate_blockers": ["file_not_saved"]},
        workspace_artifacts={},
        detail="file_not_saved",
        pipeline_attempted=False,
    )

    assert payload["pipeline_blocker"] == "file_not_saved"
    assert "pipeline blocker: <code>file_not_saved</code>" in bot.subtitle_dub_debug_text(payload)


def test_admin_debug_reports_provider_missing_blocker(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, tts=False)
    _patch_send(monkeypatch)
    _patch_blackbox(
        monkeypatch,
        calls,
        ok=False,
        status="NO_AUDIO_BYTES",
        error_code="provider_api_key_missing",
        admin_debug_summary="provider_api_key_missing",
    )

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["pipeline_attempted"] is True
    assert result["debug_job"]["input_file_path"]
    assert result["debug_job"]["pipeline_blocker"] == "provider_key_missing"


def test_admin_paid_smoke_confirm_paid_attempts_route():
    source = inspect.getsource(bot.cmd_tool_test_full_dub_video)

    assert "if not is_admin_user(update.effective_user.id)" in source
    assert "--confirm-paid" in source
    assert "build_subtitle_dubbed_video_pipeline" in source


def test_public_failure_copy_clean_no_technical_words(monkeypatch, tmp_path):
    calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, tts=False)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False, error_code="provider_api_key_missing", admin_debug_summary="provider_api_key_missing")

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, output_type="video_subtitle", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    lowered = result["text"].lower()
    for forbidden in ("admin", "test", "blackbox", "provider", "api", "asr", "tts", "mux", "ffmpeg", "debug", "code", "adapter", "traceback", "payload", "chưa xử lý file"):
        assert forbidden not in lowered


def test_no_charge_before_valid_artifact(monkeypatch, tmp_path):
    calls = []
    charge_calls = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, charge_calls=charge_calls)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=False)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is False
    assert charge_calls == []


def test_no_fake_mp4_success(monkeypatch, tmp_path):
    calls = []
    charge_calls = []
    saved_jobs = []
    _patch_engine_ready(monkeypatch, tmp_path, access_allowed=False, charge_calls=charge_calls, saved_jobs=saved_jobs)
    _patch_send(monkeypatch)
    _patch_blackbox(monkeypatch, calls, ok=True, audio=True, video=False)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        _context(),
        _state(bot.VIDEO_SUBTITLE_MODE_DUB, output_type="video", voice_style="Nữ mặc định", _pipeline_workspace=str(tmp_path)),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    assert result["partial_result"] is True
    assert result["has_audio"] is True
    assert result["has_video"] is False
    assert result["charged"] == 0
    assert charge_calls == []
    assert saved_jobs[-1]["status"] == "partial"
    assert saved_jobs[-1]["final_mp4_exists"] is False
