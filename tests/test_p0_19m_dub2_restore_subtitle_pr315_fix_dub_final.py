import asyncio
import time

import bot
import pytest


@pytest.fixture(autouse=True)
def _restore_subdub_jobs():
    original = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original)


def test_dub2_subtitle_only_does_not_use_dub_fail_fallback():
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|subtitle_translate"] = {
        "job_key": "42|chat|video|subtitle_translate",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "status": "running",
        "progress_stage": "translating",
        "progress_percent": 65,
        "updated_at": time.time(),
    }

    assert bot.subtitle_dub_find_latest_dub_job_for_user_mode(
        42,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        {"source_file_id": "video"},
    ) == {}


def test_dub2_finds_active_dub_job_when_current_key_drifted(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|dub_audio"] = {
        "job_key": "42|chat|video|dub_audio",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
        "updated_at": time.time(),
    }

    found = bot.subtitle_dub_find_latest_dub_job_for_user_mode(
        42,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        {"source_file_id": "video"},
    )

    assert found["job_key"] == "42|chat|video|dub_audio"
    assert bot.subdub_should_suppress_generic_fail_for_active_job(found, {"detail": "late_fail"})


def test_dub2_send_fail_once_suppresses_dub_error_when_key_drifted(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|dub_audio"] = {
        "job_key": "42|chat|video|dub_audio",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
        "updated_at": time.time(),
    }
    sent = []

    class Message:
        async def reply_text(self, text, **kwargs):
            sent.append(text)
            return type("Sent", (), {"message_id": 123})()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            Message(),
            "42|chat|video|different_active_flow",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="VIDEO_RENDER_FAILED",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert sent == []
    job = bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|dub_audio"]
    assert job["public_error_sent"] is False
    assert job["generic_fail_suppressed_while_active_or_delivered"] is True
