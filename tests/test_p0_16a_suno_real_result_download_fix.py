import asyncio
import inspect
from datetime import datetime, timedelta
from pathlib import Path

import bot
from providers import key4u_provider


def _job(age_minutes=1, status="submitted"):
    return {
        "internal_job_id": "MUS-UNIT16A",
        "feature": "music_suno",
        "user_id": "1",
        "chat_id": "1",
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-secret-16a",
        "status": status,
        "created_at": (datetime.now() - timedelta(minutes=age_minutes)).strftime("%Y-%m-%d %H:%M:%S"),
        "output_bytes": 0,
        "poll_count": 0,
    }


def _patch_job(monkeypatch, job):
    saved = {}

    def fake_get(_job_id):
        return dict(saved or job)

    def fake_save(payload):
        saved.clear()
        saved.update(payload)
        return payload

    monkeypatch.setattr(bot, "get_engine_async_job", fake_get)
    monkeypatch.setattr(bot, "save_engine_async_job", fake_save)
    monkeypatch.setattr(bot, "record_music_provider_attempt", lambda **_kwargs: None)
    return saved


def test_suno_poll_processing_shows_age_next_poll(monkeypatch):
    saved = _patch_job(monkeypatch, _job(age_minutes=2))

    async def fake_poll(_state, updated_by=""):
        return {
            "ok": False,
            "status": "PROCESSING",
            "output_url": "",
            "detail": "",
            "parsed_fields": {"status": True, "state": True},
        }

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))
    text = bot.engine_async_status_text(result["job"], admin=True)

    assert result["status"] == "PROCESSING"
    assert saved["status"] == "processing"
    assert saved["poll_count"] == 1
    assert saved["next_poll_after"]
    assert "Age:" in text
    assert "Next poll after:" in text
    assert "status=yes" in text


def test_suno_poll_completed_downloads_audio_bytes(monkeypatch):
    saved = _patch_job(monkeypatch, _job())

    async def fake_poll(_state, updated_by=""):
        return {
            "ok": True,
            "status": "SUCCESS",
            "output_url": "https://cdn.example.test/song.mp3",
            "detail": "",
            "parsed_fields": {"audio_url": True, "result": True},
        }

    async def fake_download(_url, timeout_seconds=60.0):
        return b"real-audio-bytes", "http=200; bytes=16; content_type=audio/mpeg", 200

    async def fake_duration(*_args, **_kwargs):
        return 120

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["ok"] is True
    assert result["status"] == "COMPLETED"
    assert result["audio_bytes"] == b"real-audio-bytes"
    assert saved["status"] == "completed"
    assert saved["output_bytes"] == len(b"real-audio-bytes")


def test_suno_poll_success_no_url_result_missing(monkeypatch):
    saved = _patch_job(monkeypatch, _job())

    async def fake_poll(_state, updated_by=""):
        return {"ok": False, "status": "SUCCESS", "output_url": "", "detail": "", "parsed_fields": {"result": True}}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["status"] == "RESULT_URL_MISSING"
    assert saved["status"] == "failed"
    assert saved["error_category"] == "result_url_missing"
    assert saved["output_bytes"] == 0


def test_suno_poll_download_fail_sanitized(monkeypatch):
    saved = _patch_job(monkeypatch, _job())

    async def fake_poll(_state, updated_by=""):
        return {"ok": True, "status": "SUCCESS", "output_url": "https://cdn.example.test/song.mp3", "detail": ""}

    async def fake_download(_url, timeout_seconds=60.0):
        return b"", "HTTP 403 Bearer very-secret token=abc123 https://private.example/audio.mp3", 403

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["status"] == "ARTIFACT_DOWNLOAD_FAILED"
    assert saved["error_category"] == "artifact_download_failed"
    assert "very-secret" not in saved["last_provider_status"]
    assert "token=abc123" not in saved["last_provider_status"]
    assert "private.example" not in saved["last_provider_status"]


def test_suno_poll_provider_failed_sanitized(monkeypatch):
    raw_task = "provider-task-secret-16a"
    saved = _patch_job(monkeypatch, _job())

    async def fake_poll(_state, updated_by=""):
        return {
            "ok": False,
            "status": "FAILED",
            "output_url": "",
            "detail": f"failed task {raw_task} Bearer bad-token token=abc123 https://private.example",
        }

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["status"] == "PROVIDER_FAILED"
    assert saved["error_category"] == "provider_failed"
    assert raw_task not in saved["last_provider_status"]
    assert "bad-token" not in saved["last_provider_status"]
    assert "token=abc123" not in saved["last_provider_status"]


def test_suno_poll_no_raw_task_id_public():
    raw_task = "provider-task-secret-16a"
    text = bot.engine_async_status_text({
        "internal_job_id": "MUS-UNIT16A",
        "feature": "music_suno",
        "provider": "key4u_suno",
        "provider_task_id": raw_task,
        "status": "processing",
        "last_provider_status": f"processing {raw_task}",
        "output_bytes": 0,
    }, admin=False)

    assert raw_task not in text
    assert "Provider task" not in text


def test_suno_poll_no_secret_leak():
    text = bot.sanitize_provider_status_text(
        "Bearer secret-token API_KEY=abc SECRET=def token=ghi https://private.example/audio.mp3",
        "provider-task-secret-16a",
    )
    lowered = text.lower()

    assert "secret-token" not in text
    assert "abc" not in text
    assert "def" not in text
    assert "ghi" not in text
    assert "private.example" not in text
    assert "bearer ***" in lowered


def test_suno_soft_timeout_warning(monkeypatch):
    saved = _patch_job(monkeypatch, _job(age_minutes=6))

    async def fake_poll(_state, updated_by=""):
        return {"ok": False, "status": "PROCESSING", "output_url": "", "detail": ""}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["status"] == "PROCESSING"
    assert saved["status"] == "processing"
    assert "lâu hơn 5 phút" in saved["progress_text"]
    assert "TOAN AAS chưa trừ Xu" in saved["progress_text"]


def test_suno_hard_timeout_marks_timeout_no_charge(monkeypatch):
    saved = _patch_job(monkeypatch, _job(age_minutes=25))

    async def fake_poll(_state, updated_by=""):
        return {"ok": False, "status": "PROCESSING", "output_url": "", "detail": ""}

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["status"] == "TIMEOUT_PROVIDER_PROCESSING"
    assert saved["status"] == "timeout_provider_processing"
    assert saved["error_category"] == "timeout_provider_processing"
    assert "TOAN AAS chưa trừ Xu" in saved["progress_text"]


def test_suno_timeout_can_still_be_polled_admin(monkeypatch):
    saved = _patch_job(monkeypatch, _job(age_minutes=25, status="timeout_provider_processing"))

    async def fake_poll(_state, updated_by=""):
        return {"ok": True, "status": "SUCCESS", "output_url": "https://cdn.example.test/song.mp3", "detail": ""}

    async def fake_download(_url, timeout_seconds=60.0):
        return b"late-real-audio", "http=200; bytes=15; content_type=audio/mpeg", 200

    async def fake_duration(*_args, **_kwargs):
        return 120

    monkeypatch.setattr(bot, "poll_music_generation_job", fake_poll)
    monkeypatch.setattr(bot, "_download_music_audio_url_bytes", fake_download)
    monkeypatch.setattr(bot, "music_audio_real_duration_seconds", fake_duration)

    result = asyncio.run(bot.poll_music_suno_async_job("MUS-UNIT16A", download=True))

    assert result["ok"] is True
    assert saved["status"] == "completed"
    assert saved["output_bytes"] == len(b"late-real-audio")


def test_suno_fallback_only_if_verified(monkeypatch):
    monkeypatch.setattr(
        bot,
        "get_suno_music_readiness",
        lambda: {"providers": {"key4u_suno": {"configured": True}, "shopaikey_music": {"configured": True}}},
    )
    monkeypatch.setattr(bot, "get_tool_test_result", lambda name: {"status": "PASS_FULL_RESULT"} if name == "shopaikey_music_job" else {"status": "NOT_TESTED"})
    monkeypatch.setattr(bot, "preferred_tool_test_result", lambda *_names: {"status": "PASS", "detail": "bytes=2048"})

    assert bot.suno_verified_fallback_provider("key4u_suno") == "shopaikey_music"


def test_suno_fallback_requires_confirm():
    source = inspect.getsource(bot.poll_music_suno_async_job)
    text = bot.suno_fallback_status_text("key4u_suno")

    assert "Chỉ chạy khi admin xác nhận rõ" in text or "Chưa có provider" in text
    assert "submit_music_generation_job" not in source
    assert "suno_verified_fallback_provider" not in source


def test_suno_no_fallback_clear_message(monkeypatch):
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"providers": {"key4u_suno": {"configured": True}}})
    monkeypatch.setattr(bot, "get_tool_test_result", lambda _name: {"status": "NOT_TESTED"})
    monkeypatch.setattr(bot, "preferred_tool_test_result", lambda *_names: {"status": "NOT_TESTED", "detail": ""})

    assert bot.suno_verified_fallback_provider("key4u_suno") == ""
    assert bot.suno_fallback_status_text("key4u_suno") == "Chưa có provider nhạc AI fallback đã xác minh."


def test_key4u_suno_query_parser_supports_nested_result_audio_fields():
    payload = {
        "status": "SUCCESS",
        "result": {"output": [{"download_url": "https://cdn.example.test/final-song.mp3"}]},
    }

    urls = key4u_provider._suno_audio_urls_from_payload(payload)
    fields = key4u_provider._suno_payload_field_presence(payload)

    assert urls == ["https://cdn.example.test/final-song.mp3"]
    assert fields["status"] is True
    assert fields["result"] is True
    assert fields["output"] is True
    assert fields["download_url"] is True
    assert key4u_provider._normalize_suno_query_status("SUCCESS", has_audio=False) == "SUCCESS"


def test_p0_16a_commands_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for needle in (
        'CommandHandler("key4u_suno_route_status", cmd_key4u_suno_route_status)',
        'CommandHandler("key4u_suno_job_status", cmd_key4u_suno_job_status)',
        'CommandHandler("key4u_suno_download_probe", cmd_key4u_suno_download_probe)',
        'CommandHandler("music_suno_poll", cmd_music_suno_poll)',
        'CommandHandler("music_suno_timeout", cmd_music_suno_timeout)',
    ):
        assert needle in source
