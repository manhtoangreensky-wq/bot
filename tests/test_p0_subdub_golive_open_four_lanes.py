"""P0.SUBDUB.GOLIVE — /subdub_public_open_safe is a real, safe switch.

The command must actually open all four public lanes (runtime override in
system_settings, no Railway ENV edit, no redeploy), only when each lane's
hard requirements (config + smoke PASS on current runtime SHA) hold, and
/subdub_public_close must re-guard everything instantly. Zero provider
calls, zero wallet mutations, zero real Telegram sends (fake update).
"""

import asyncio
from types import SimpleNamespace

import bot

ALL_LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)

NOT_TESTED = {"status": "NOT_TESTED", "tested_at": "", "detail": ""}


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(str(text))
        return SimpleNamespace(message_id=len(self.replies))


def _fake_update(user_id=22):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=FakeMessage(),
    )


def _patch_settings_store(monkeypatch):
    store = {}

    def get_system_setting(key, default=""):
        return store.get(str(key), default)

    def set_system_setting(key, value, note="", updated_by=""):
        store[str(key)] = str(value)

    monkeypatch.setattr(bot, "get_system_setting", get_system_setting)
    monkeypatch.setattr(bot, "set_system_setting", set_system_setting)
    return store


def _patch_production_like_runtime(monkeypatch):
    """ENV flags OFF + freeze ON (today's Railway state), providers configured,
    smokes PASS on the current runtime SHA."""
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "golive-runtime-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", False)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "direct_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_GROUP_ID", "configured")
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
    smoke = {
        "asr:deepgram": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=golive-runtime-sha"},
        "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=golive-runtime-sha"},
        "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=golive-runtime-sha"},
    }
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: dict(smoke.get(name) or dict(NOT_TESTED)),
    )
    return smoke


def test_open_safe_opens_all_four_lanes_when_smokes_pass(monkeypatch):
    store = _patch_settings_store(monkeypatch)
    _patch_production_like_runtime(monkeypatch)
    for mode in ALL_LANES:
        assert bot.get_subdub_lane_readiness(mode, {}, public=True)["effective_ready"] is False
    update = _fake_update()
    asyncio.run(bot.cmd_subdub_public_open_safe(update, SimpleNamespace()))
    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(mode, {}, public=True)
        assert readiness["effective_ready"] is True, (mode, readiness["blockers"])
    body = "\n".join(update.message.replies)
    assert "OPEN" in body
    assert store, "overrides must be persisted in the settings store"
    assert bot.PROVIDER_FREEZE is True, "global ENV freeze must stay untouched"


def test_open_safe_keeps_dub_and_combo_closed_without_tts_smoke(monkeypatch):
    _patch_settings_store(monkeypatch)
    smoke = _patch_production_like_runtime(monkeypatch)
    smoke["tts:direct_minimax"] = dict(NOT_TESTED)
    update = _fake_update()
    asyncio.run(bot.cmd_subdub_public_open_safe(update, SimpleNamespace()))
    ready = {
        mode: bot.get_subdub_lane_readiness(mode, {}, public=True)["effective_ready"]
        for mode in ALL_LANES
    }
    assert ready[bot.VIDEO_SUBTITLE_MODE_CREATE] is True
    assert ready[bot.VIDEO_SUBTITLE_MODE_TRANSLATE] is True
    assert ready[bot.VIDEO_SUBTITLE_MODE_DUB] is False
    assert ready[bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB] is False


def test_public_close_reguards_all_lanes_instantly(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_production_like_runtime(monkeypatch)
    asyncio.run(bot.cmd_subdub_public_open_safe(_fake_update(), SimpleNamespace()))
    asyncio.run(bot.cmd_subdub_public_close(_fake_update(), SimpleNamespace()))
    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(mode, {}, public=True)
        assert readiness["effective_ready"] is False
        assert "public_flag_off" in readiness["blockers"]


def test_freeze_override_is_scoped_to_subdub_public_readiness_only(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_production_like_runtime(monkeypatch)
    asyncio.run(bot.cmd_subdub_public_open_safe(_fake_update(), SimpleNamespace()))
    assert bot.PROVIDER_FREEZE is True
    assert bot.PROVIDER_FREEZE_ENABLED is True
    assert bot.subdub_public_freeze_override_active() is True
    freeze = bot.subdub_effective_freeze_status(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert freeze["global_provider_freeze"] is True


def test_open_safe_requires_admin(monkeypatch):
    store = _patch_settings_store(monkeypatch)
    _patch_production_like_runtime(monkeypatch)
    update = _fake_update(user_id=999)
    asyncio.run(bot.cmd_subdub_public_open_safe(update, SimpleNamespace()))
    assert store == {}
    assert update.message.replies == []
    for mode in ALL_LANES:
        assert bot.get_subdub_lane_readiness(mode, {}, public=True)["effective_ready"] is False


def test_open_safe_never_calls_providers_or_engine():
    import inspect

    source = inspect.getsource(bot.cmd_subdub_public_open_safe)
    for forbidden in (
        "execute_engine",
        "execute_video_dubbing_pipeline",
        "asr_transcribe_audio",
        "translate_subtitle_text",
        "video_dubbing_tts_bytes",
        "httpx",
        "requests.",
    ):
        assert forbidden not in source


def test_env_defaults_still_apply_when_no_override_present(monkeypatch):
    _patch_settings_store(monkeypatch)
    _patch_production_like_runtime(monkeypatch)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    readiness = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_CREATE, {}, public=True
    )
    assert readiness["effective_ready"] is True, readiness["blockers"]


# ---- ADDENDUM 1: intake download robustness / real ceiling / honest copy ----


class _FakeTgFile:
    def __init__(self, size, data=b"", fail=None, fail_times=0):
        self.file_size = size
        self._data = data
        self._fail = fail
        self._fail_times = fail_times
        self.calls = 0

    async def download_as_bytearray(self, **kwargs):
        self.calls += 1
        if self._fail and self.calls <= self._fail_times:
            raise self._fail
        return bytearray(self._data)


def _dl_state(size, duration=30):
    return {
        "video_file_id": "file-1",
        "video_file_size": size,
        "video_duration": duration,
        "source_mime_type": "video/mp4",
        "source_file_name": "input.mp4",
    }


def _bot_ctx(tg_file, get_file_calls):
    async def get_file(file_id, **kwargs):
        get_file_calls.append(file_id)
        return tg_file

    return SimpleNamespace(bot=SimpleNamespace(get_file=get_file))


def test_download_timeout_retries_then_fails_with_timeout_class(monkeypatch):
    monkeypatch.setattr(bot.asyncio, "sleep", _instant_sleep, raising=False)
    tg_file = _FakeTgFile(14_611_967, data=b"", fail=TimeoutError("Timed out"), fail_times=99)
    calls = []
    try:
        asyncio.run(bot.video_dubbing_download_source(_bot_ctx(tg_file, calls), _dl_state(14_611_967)))
        raised = ""
    except RuntimeError as exc:
        raised = str(exc)
    assert raised == "telegram_download_failed:timeout"
    assert len(calls) == int(bot.SUBDUB_TELEGRAM_DOWNLOAD_RETRIES)


def test_download_transient_timeout_recovers_within_retries(monkeypatch):
    monkeypatch.setattr(bot.asyncio, "sleep", _instant_sleep, raising=False)
    tg_file = _FakeTgFile(1024, data=b"x" * 1024, fail=TimeoutError("Timed out"), fail_times=1)
    calls = []
    data, mime = asyncio.run(
        bot.video_dubbing_download_source(_bot_ctx(tg_file, calls), _dl_state(1024))
    )
    assert data == b"x" * 1024
    assert mime == "video/mp4"
    assert len(calls) == 2


def test_oversize_file_rejected_before_any_download(monkeypatch):
    limit = int(bot.SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB) * 1024 * 1024
    calls = []
    tg_file = _FakeTgFile(limit + 1)
    try:
        asyncio.run(bot.video_dubbing_download_source(_bot_ctx(tg_file, calls), _dl_state(limit + 1)))
        raised = ""
    except RuntimeError as exc:
        raised = str(exc)
    assert "file is too big" in raised
    assert calls == []
    assert tg_file.calls == 0


async def _instant_sleep(_seconds):
    return None


def test_download_failure_public_copy_is_honest_and_clean():
    text = bot.subdub_download_failure_public_text("vi")
    assert "chưa trừ Xu" in text
    assert "gửi lại" in text
    lowered = text.lower()
    for forbidden in ("bot_api_direct", "deepgram", "timeout", "provider", "env", "rõ tiếng"):
        assert forbidden not in lowered
    job = {
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "pipeline_blocker": "telegram_download_failed:timeout",
    }
    assert bot.subdub_job_public_status_text(job, "vi") == text


def test_timeout_is_never_mislabelled_as_large_download():
    job = {"input_save_blocker": "telegram_download_failed:timeout", "status": "failed"}
    normalized = bot.subdub_normalize_input_save_failed_terminal(
        {**job, "lifecycle_state": "input_save_failed", "current_stage": "input_save_failed"}
    )
    blocker = str(normalized.get("no_charge_reason") or normalized.get("pipeline_blocker") or "")
    assert "large_telegram_download_unsupported" not in blocker
    assert "timeout" in blocker


def test_advertised_limit_comes_from_single_runtime_source(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_MAX_INPUT_MB", 50)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 20)
    assert bot.subdub_input_limit_mb() == 20
    assert f"{bot.subdub_input_limit_mb()} MB" in bot.subdub_media_limits_notice("vi")
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 18)
    assert bot.subdub_input_limit_mb() == 18
    assert "18 MB" in bot.subdub_media_limits_notice("vi")
    assert "50 MB" not in bot.subdub_media_limits_notice("vi")
