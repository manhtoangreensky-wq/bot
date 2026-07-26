import asyncio
import inspect
from types import SimpleNamespace

import pytest

import bot


ALL_LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)


def _lane_state(mode):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_mime_type": "video/mp4",
        "source_file_name": "fixture.mp4",
        "target_language": "vi",
        "translate_requested": "1" if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else "0",
    }


def _patch_ready_runtime(monkeypatch):
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "live22-runtime-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "direct_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_GROUP_ID", "configured")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(
        bot,
        "subdub_runtime_status_payload",
        lambda: {
            "media_preprocessing_ready": True,
            "subtitle_rendering_ready": True,
            "ffmpeg_ready": True,
            "ffprobe_ready": True,
        },
    )

    smoke = {
        "asr:deepgram": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=live22-runtime-sha"},
        "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=live22-runtime-sha"},
        "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=live22-runtime-sha"},
    }
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: dict(smoke.get(name) or {"status": "NOT_TESTED", "tested_at": "", "detail": ""}),
    )
    return smoke


def test_live_fixture_with_flags_off_freeze_on_blocks_all_four_lanes(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    for name in (
        "VIDEO_SUBTITLE_PUBLIC_ENABLED",
        "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED",
        "VIDEO_DUB_PUBLIC_ENABLED",
        "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED",
    ):
        monkeypatch.setattr(bot, name, False)

    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(mode, _lane_state(mode), public=True)
        assert readiness["effective_ready"] is False
        assert "public_flag_off" in readiness["blockers"]
        assert "provider_freeze" in readiness["blockers"]


def test_canonical_readiness_exposes_required_contract_fields(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    readiness = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        public=True,
    )

    expected = {
        "mode", "public_flag_enabled", "maintenance_enabled", "global_provider_freeze",
        "subdub_freeze", "media_runtime_ready", "asr_required", "asr_provider",
        "asr_configured", "asr_smoke_status", "asr_public_allowed",
        "translation_required", "translation_provider", "translation_configured",
        "translation_smoke_status", "translation_public_allowed", "tts_required",
        "tts_provider", "tts_configured", "tts_smoke_status", "tts_public_allowed",
        "effective_ready", "blockers", "public_reason", "admin_reason",
    }
    assert expected <= set(readiness)
    assert readiness["effective_ready"] is True


def test_subtitle_and_translate_do_not_require_tts(monkeypatch):
    smoke = _patch_ready_runtime(monkeypatch)
    smoke["tts:direct_minimax"] = {"status": "NOT_TESTED", "tested_at": "", "detail": ""}

    subtitle = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_CREATE),
        public=True,
    )
    translated = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE),
        public=True,
    )

    assert subtitle["tts_required"] is False
    assert translated["tts_required"] is False
    assert subtitle["effective_ready"] is True
    assert translated["effective_ready"] is True


def test_tts_not_tested_blocks_only_dub_and_combo(monkeypatch):
    smoke = _patch_ready_runtime(monkeypatch)
    smoke["tts:direct_minimax"] = {"status": "NOT_TESTED", "tested_at": "", "detail": ""}

    results = {
        mode: bot.get_subdub_lane_readiness(mode, _lane_state(mode), public=True)
        for mode in ALL_LANES
    }

    assert results[bot.VIDEO_SUBTITLE_MODE_CREATE]["effective_ready"] is True
    assert results[bot.VIDEO_SUBTITLE_MODE_TRANSLATE]["effective_ready"] is True
    assert results[bot.VIDEO_SUBTITLE_MODE_DUB]["effective_ready"] is False
    assert results[bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB]["effective_ready"] is False
    assert "tts_smoke_not_pass" in results[bot.VIDEO_SUBTITLE_MODE_DUB]["blockers"]


def test_ambiguous_auto_provider_is_not_public_ready(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "auto")

    readiness = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        public=True,
    )

    assert readiness["effective_ready"] is False
    assert "asr_provider_policy_required" in readiness["blockers"]
    assert "tts_provider_policy_required" in readiness["blockers"]


def test_product_gate_cannot_override_denied_access():
    matrix = {
        "product_route_allowed": True,
        "product_config_ready": True,
        "media_prerequisites_ready": True,
        "input_file_saved": True,
        "input_file_exists": True,
        "input_file_size": 1024,
        "access_allowed": False,
    }

    assert bot.video_dubbing_product_gate_allows_pipeline({"allowed": False}, matrix) is False


def test_product_gate_requires_provider_configuration():
    matrix = {
        "product_route_allowed": True,
        "product_config_ready": False,
        "media_prerequisites_ready": True,
        "input_file_saved": True,
        "input_file_exists": True,
        "input_file_size": 1024,
        "access_allowed": True,
    }

    assert bot.video_dubbing_product_gate_allows_pipeline({"allowed": True}, matrix) is False


def test_prechecked_flag_cannot_bypass_subdub_provider_gate(monkeypatch):
    calls = {"gate": 0, "runner": 0}

    def deny_gate(*_args, **_kwargs):
        calls["gate"] += 1
        return {
            "allowed": False,
            "status": "blocked_public_maintenance",
            "reason": "public_flag_off",
            "message": "guarded",
            "readiness": {},
        }

    async def runner():
        calls["runner"] += 1
        return {"ok": True, "has_video": True}

    monkeypatch.setattr(bot, "evaluate_engine_gate", deny_gate)
    monkeypatch.setattr(bot, "_product_engine_readiness", lambda *_args, **_kwargs: {})

    result = asyncio.run(
        bot.execute_engine(
            "subtitle_translate",
            {"runner": runner, "state": _lane_state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)},
            {"user_id": 22, "gate_prechecked": True, "confirm_paid": True},
        )
    )

    assert result["ok"] is False
    assert calls == {"gate": 1, "runner": 0}


def test_all_four_public_lane_callbacks_use_canonical_readiness(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_subdub_lane_readiness",
        lambda *_args, **_kwargs: {"effective_ready": False},
        raising=False,
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)

    for mode in ALL_LANES:
        assert bot.video_dubbing_public_flow_locked(22, mode, _lane_state(mode)) is True

    callback_source = inspect.getsource(bot.handle_video_dubbing_callback)
    upload_source = inspect.getsource(bot.handle_video_dubbing_pending_upload)
    assert "get_subdub_lane_readiness" in callback_source
    assert "get_subdub_lane_readiness" in upload_source


def test_selected_asr_failure_does_not_fallback_to_another_paid_provider(monkeypatch):
    calls = {"key4u": 0, "deepgram": 0}
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "configured")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    async def key4u_fail(*_args, **_kwargs):
        calls["key4u"] += 1
        return {"ok": False, "status": "FAIL", "text": "", "detail": "fixture"}

    async def deepgram_should_not_run(*_args, **_kwargs):
        calls["deepgram"] += 1
        return {"ok": True, "status": "PASS", "transcript": "unexpected", "transcript_json": {}}

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", key4u_fail)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", deepgram_should_not_run)

    result = asyncio.run(bot.asr_transcribe_audio(b"audio", allow_admin=True))

    assert result["ok"] is False
    assert calls == {"key4u": 1, "deepgram": 0}


def test_subtitle_translation_does_not_fallback_after_selected_deepl_fails(monkeypatch):
    calls = {"deepl": 0, "gemini": 0}
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "gemini_client", object())
    monkeypatch.setattr(bot, "openai_client", None)
    monkeypatch.setattr(bot, "key4u_subtitle_translation_configured", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_public_chat_fallback_enabled", lambda: False)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    async def deepl_fail(*_args, **_kwargs):
        calls["deepl"] += 1
        raise RuntimeError("fixture")

    async def gemini_should_not_run(*_args, **_kwargs):
        calls["gemini"] += 1
        return "unexpected"

    monkeypatch.setattr(bot, "translate_with_deepl", deepl_fail)
    monkeypatch.setattr(bot, "translate_with_gemini", gemini_should_not_run)

    with pytest.raises(RuntimeError):
        asyncio.run(bot.translate_subtitle_text("hello", "vi", allow_admin=False))

    assert calls == {"deepl": 1, "gemini": 0}


def test_selected_tts_failure_does_not_fallback_to_another_route(monkeypatch):
    calls = {"direct": 0, "key4u": 0, "shopaikey": 0}
    monkeypatch.setattr(bot, "TTS_PROVIDER", "direct_minimax")
    monkeypatch.setattr(bot, "direct_minimax_tts_configured", lambda: True)
    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=False: False)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_configured", lambda: False)

    async def direct_fail(*_args, **_kwargs):
        calls["direct"] += 1
        return "FAIL", b"", "fixture", 500

    async def key4u_should_not_run(*_args, **_kwargs):
        calls["key4u"] += 1
        return "PASS", b"unexpected", "", 200

    async def shopaikey_should_not_run(*_args, **_kwargs):
        calls["shopaikey"] += 1
        return "PASS", b"unexpected", "", 200

    monkeypatch.setattr(bot, "call_direct_minimax_tts_bytes_with_speed", direct_fail)
    monkeypatch.setattr(bot, "call_key4u_minimax_tts_bytes_with_speed", key4u_should_not_run)
    monkeypatch.setattr(bot, "call_shopaikey_minimax_tts_bytes_with_speed", shopaikey_should_not_run)

    with pytest.raises(RuntimeError, match="tts_unavailable"):
        asyncio.run(bot.video_dubbing_tts_bytes("hello", allow_admin=True))

    assert calls == {"direct": 1, "key4u": 0, "shopaikey": 0}


def test_debug_text_is_plain_and_split_below_telegram_limit():
    chunks = bot.subdub_admin_debug_chunks("<b>debug & value</b>\n" * 600, limit=3200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 3200 for chunk in chunks)
    assert all("<b>" not in chunk for chunk in chunks)
    assert "debug & value" in chunks[0]


def test_subdub_status_debug_handles_long_malformed_html_without_badrequest(monkeypatch):
    class StrictMessage:
        def __init__(self):
            self.parts = []

        async def reply_text(self, text, **kwargs):
            if kwargs.get("parse_mode") == "HTML" or len(str(text)) > 3600:
                raise RuntimeError("BadRequest")
            self.parts.append(str(text))
            return SimpleNamespace(message_id=len(self.parts))

    message = StrictMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=22), message=message)
    context = SimpleNamespace(args=[])
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "subtitle_dub_debug_lookup_job", lambda *_args, **_kwargs: {"job_id": "fixture"})
    monkeypatch.setattr(bot, "subtitle_dub_debug_text", lambda _job: "<b>broken & debug</b>\n" * 500)

    asyncio.run(bot.cmd_subdub_status_debug(update, context))

    assert len(message.parts) > 1
    assert all(len(part) <= 3600 for part in message.parts)


def test_subdub_status_reports_railway_local_worker_ownership(monkeypatch):
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path": ""})
    monkeypatch.setattr(bot, "video_dubbing_mux_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_subtitle_render_ready", lambda: True)
    monkeypatch.setattr(
        bot,
        "get_asr_adapter_readiness",
        lambda **_kwargs: {
            "adapter": "deepgram", "smoke_status": "PASS", "public_ready": True,
            "configured": True, "smoke_ready": True, "supports_audio": True, "supports_video": True,
        },
    )
    monkeypatch.setattr(bot, "preferred_tool_test_status_text", lambda *_args: "PASS")
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=False: True)

    payload = bot.video_pipeline_status_payload()

    assert payload["execution_owner"] == "railway_local"
    assert payload["external_worker_required"] is False
    assert payload["external_worker_connection"] == "N/A"
