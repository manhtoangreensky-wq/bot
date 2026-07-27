"""P0.SUBDUB.PUBLICLIVE24: owner-confirmed public opening is advisory-smoke only.

The force-open operation is deliberately scoped to SubDub. It must not call
providers, create jobs, mutate Xu, or relax provider selection outside the
four explicitly confirmed SubDub product lanes.
"""

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot


ALL_LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(str(text))
        return SimpleNamespace(message_id=len(self.replies))


def _update(user_id=22):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=FakeMessage(),
    )


def _settings(monkeypatch):
    store = {}

    monkeypatch.setattr(
        bot,
        "get_system_setting",
        lambda key, default="": store.get(str(key), default),
    )
    monkeypatch.setattr(
        bot,
        "set_system_setting",
        lambda key, value, note="", updated_by="": store.__setitem__(str(key), str(value)),
    )
    return store


def _production_runtime(monkeypatch, smoke_status="FAIL"):
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "publiclive24-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", False)
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "key4u_minimax")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: True)
    monkeypatch.setattr(
        bot,
        "key4u_minimax_tts_configured",
        lambda require_public=True: not require_public,
    )
    monkeypatch.setattr(bot, "is_admin_user", lambda uid: uid == 22)
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
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: {
            "status": smoke_status,
            "tested_at": "now",
            "detail": "runtime_sha=publiclive24-sha",
        },
    )


def test_force_open_requires_literal_owner_confirmation(monkeypatch):
    store = _settings(monkeypatch)
    _production_runtime(monkeypatch)
    update = _update()

    asyncio.run(bot.cmd_subdub_public_open_force(update, SimpleNamespace(args=[])))

    assert store == {}
    assert "--confirm-production" in "\n".join(update.message.replies)


@pytest.mark.parametrize("smoke_status", ["NOT_TESTED", "STALE", "FAIL"])
def test_force_open_keeps_all_lanes_public_with_advisory_smoke(monkeypatch, smoke_status):
    store = _settings(monkeypatch)
    _production_runtime(monkeypatch, smoke_status=smoke_status)
    update = _update()

    asyncio.run(
        bot.cmd_subdub_public_open_force(
            update,
            SimpleNamespace(args=["--confirm-production"]),
        )
    )

    assert bot.subdub_public_force_override_active() is True
    assert bot.subdub_public_freeze_override_active() is True
    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(mode, {}, public=True)
        assert readiness["public_flag_enabled"] is True
        assert readiness["effective_ready"] is True, (mode, readiness["blockers"])
        assert readiness["smoke_hard_lock"] is False
    assert store, "force-open flags must persist in system_settings"
    body = "\n".join(update.message.replies)
    assert "SUBDUB PUBLIC OPEN = YES" in body
    assert "provider_calls=0" in body
    assert "jobs_created=0" in body
    assert "wallet_mutation=0" in body


def test_force_open_refuses_auto_provider_policy(monkeypatch):
    store = _settings(monkeypatch)
    _production_runtime(monkeypatch)
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "auto")
    update = _update()

    asyncio.run(
        bot.cmd_subdub_public_open_force(
            update,
            SimpleNamespace(args=["--confirm-production"]),
        )
    )

    assert store == {}
    assert "explicit_provider_required" in "\n".join(update.message.replies)


def test_failed_smoke_after_force_open_does_not_close_lane(monkeypatch):
    _settings(monkeypatch)
    _production_runtime(monkeypatch, smoke_status="PASS")
    asyncio.run(
        bot.cmd_subdub_public_open_force(
            _update(),
            SimpleNamespace(args=["--confirm-production"]),
        )
    )
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: {
            "status": "FAIL",
            "tested_at": "later",
            "detail": "runtime_sha=publiclive24-sha",
        },
    )

    for mode in ALL_LANES:
        assert bot.get_subdub_lane_readiness(mode, {}, public=True)["effective_ready"] is True


def test_force_open_has_no_provider_engine_job_or_wallet_side_effects():
    source = inspect.getsource(bot.cmd_subdub_public_open_force)
    forbidden = (
        "execute_engine",
        "execute_video_dubbing_pipeline",
        "asr_transcribe_audio",
        "translate_subtitle_text",
        "video_dubbing_tts_bytes",
        "acquire_subtitle_dub_pipeline_job",
        "spend_fixed_credit",
        "httpx",
        "requests.",
    )
    assert not [name for name in forbidden if name in source]


def test_force_open_override_allows_key4u_only_when_subdub_route_opts_in(monkeypatch):
    _settings(monkeypatch)
    _production_runtime(monkeypatch)
    asyncio.run(
        bot.cmd_subdub_public_open_force(
            _update(),
            SimpleNamespace(args=["--confirm-production"]),
        )
    )
    calls = []

    async def fake_asr(*args, **kwargs):
        calls.append("asr")
        return {"ok": True, "status": "PASS", "text": "real transcript", "detail": "ok"}

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", fake_asr)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *args, **kwargs: None)

    blocked = asyncio.run(bot.asr_transcribe_audio(b"audio", "audio/mpeg"))
    allowed = asyncio.run(
        bot.asr_transcribe_audio(
            b"audio",
            "audio/mpeg",
            allow_subdub_public=True,
        )
    )

    assert blocked["ok"] is False
    assert allowed["ok"] is True
    assert calls == ["asr"]


def test_force_open_override_reaches_key4u_subdub_tts_without_global_public(monkeypatch):
    _settings(monkeypatch)
    _production_runtime(monkeypatch)
    asyncio.run(
        bot.cmd_subdub_public_open_force(
            _update(),
            SimpleNamespace(args=["--confirm-production"]),
        )
    )
    calls = []

    async def fake_tts(text, **kwargs):
        calls.append((text, bool(kwargs.get("allow_admin"))))
        return "PASS", b"playable-audio", "ok", 200

    monkeypatch.setattr(bot, "call_key4u_minimax_tts_bytes_with_speed", fake_tts)
    label, audio, _detail = asyncio.run(bot.video_dubbing_tts_bytes("xin chao"))

    assert label == "Key4U MiniMax"
    assert audio == b"playable-audio"
    assert calls == [("xin chao", True)]


def test_key4u_minimax_uses_one_canonical_submit_without_fallback(monkeypatch):
    calls = []

    class FakeProvider:
        async def voice_tts_fallback(self, *args, **kwargs):
            raise AssertionError("automatic fallback is forbidden")

        async def tts(self, *args, **kwargs):
            calls.append("minimax")
            return {
                "ok": True,
                "status": "PASS",
                "http_status": 200,
                "output_bytes": b"canonical-minimax-audio",
            }

    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=True: True)
    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: FakeProvider())

    status, audio, detail, http_status = asyncio.run(
        bot.key4u_minimax_tts_bytes("xin chao", allow_admin=True)
    )

    assert status == "PASS"
    assert audio == b"canonical-minimax-audio"
    assert http_status == 200
    assert "route=key4u_minimax" in detail
    assert calls == ["minimax"]


def test_tts_synthesis_submits_each_cue_once_without_speed_retry(monkeypatch):
    calls = []

    async def fake_tts(text, *args, **kwargs):
        calls.append(text)
        return "Key4U MiniMax", text.encode("utf-8"), "ok"

    async def fake_duration(audio_bytes):
        return 0.1 if audio_bytes == b"short" else 10.0

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)
    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [
                {"index": 1, "start": 0.0, "end": 2.0, "text": "short"},
                {"index": 2, "start": 2.0, "end": 4.0, "text": "long"},
            ],
            base_speed=0.95,
            max_speed=1.0,
        )
    )

    assert calls == ["short", "long"]
    assert len(result["chunks"]) == 2


def test_public_close_clears_force_override(monkeypatch):
    _settings(monkeypatch)
    _production_runtime(monkeypatch)
    asyncio.run(
        bot.cmd_subdub_public_open_force(
            _update(),
            SimpleNamespace(args=["--confirm-production"]),
        )
    )

    asyncio.run(bot.cmd_subdub_public_close(_update(), SimpleNamespace()))

    assert bot.subdub_public_force_override_active() is False
    for mode in ALL_LANES:
        assert bot.video_dubbing_public_flag(mode) is False


def test_force_open_command_registered_and_debug_reports_public_truth():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("subdub_public_open_force", cmd_subdub_public_open_force)' in source
    debug = bot.subdub_public_state_debug_text()
    for label in ("subtitle", "translation", "dubbing", "combo"):
        assert label in debug
    assert "automatic_paid_fallback=OFF" in debug
    assert "background_product_execution=OFF" in debug
