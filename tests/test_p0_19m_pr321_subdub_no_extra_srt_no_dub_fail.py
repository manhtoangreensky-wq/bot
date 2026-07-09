import asyncio
import inspect
import time

import bot
import pytest


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"


class _Sent:
    def __init__(self, message_id):
        self.message_id = message_id


class _Message:
    def __init__(self):
        self.videos = []
        self.documents = []
        self.audios = []
        self.texts = []

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return _Sent(901)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return _Sent(902)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return _Sent(903)

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        return _Sent(904)


@pytest.fixture(autouse=True)
def _restore_subdub_jobs():
    original = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original)


def test_pr321_subtitle_create_video_does_not_auto_send_srt_fallback():
    message = _Message()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            active_flow="subtitle_translate",
            subtitle_items=[
                {
                    "output_type": "srt",
                    "filename": "toan_aas_subtitle_translate.srt",
                    "bytes": VALID_SRT.encode("utf-8"),
                }
            ],
            srt_text=VALID_SRT,
            video_bytes=b"mp4-bytes",
            lang="vi",
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["srt_auto_send_suppressed"] is True
    assert sent["srt_suppress_reason"] == "video_delivered"
    assert sent["explicit_srt_download_available"] is True
    assert len(message.videos) == 1
    assert message.documents == []
    assert "chưa tạo được video hoàn chỉnh" not in " ".join(str(d) for d in message.documents)


def test_pr321_subtitle_translate_video_does_not_auto_send_srt_fallback():
    message = _Message()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subtitle_translate",
            subtitle_items=[
                {
                    "output_type": "srt",
                    "filename": "toan_aas_subtitle_translate.srt",
                    "bytes": VALID_SRT.encode("utf-8"),
                }
            ],
            srt_text=VALID_SRT,
            video_bytes=b"mp4-bytes",
            lang="vi",
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["srt_auto_send_suppressed"] is True
    assert len(message.videos) == 1
    assert message.documents == []


def test_pr321_video_modes_do_not_auto_send_srt_partial_without_mp4():
    message = _Message()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subtitle_translate",
            subtitle_items=[
                {
                    "output_type": "srt",
                    "filename": "toan_aas_subtitle_translate.srt",
                    "bytes": VALID_SRT.encode("utf-8"),
                }
            ],
            srt_text=VALID_SRT,
            video_bytes=b"",
            lang="vi",
        )
    )

    assert sent["srt_auto_send_suppressed"] is True
    assert sent["srt_suppress_reason"] == "video_mode_no_auto_srt_fallback"
    assert sent["explicit_srt_download_available"] is True
    assert message.documents == []


def test_pr321_outer_subdub_runtime_error_has_active_job_public_fail_guard():
    source = inspect.getsource(bot.on_telegram_error)

    assert "subdub_should_suppress_generic_fail_for_active_job" in source
    assert "generic_fail_suppressed_while_active_or_delivered" in source
    guarded = source.split("subdub_error_reason == \"subdub_runtime_failure\"", 1)[1]
    assert "return" in guarded.split("await context.bot.send_message", 1)[0]


def test_pr321_dub_fail_prefers_active_job_over_same_key_failed_job(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|current_fail"] = {
        "job_key": "42|chat|video|current_fail",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_percent": 5,
        "updated_at": time.time() + 10,
    }
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|real_dub_job"] = {
        "job_key": "42|chat|video|real_dub_job",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
        "updated_at": time.time(),
    }
    message = _Message()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            "42|chat|video|current_fail",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="VIDEO_RENDER_FAILED",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert message.texts == []
    job = bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|real_dub_job"]
    assert job["generic_fail_suppressed_while_active_or_delivered"] is True
    assert job["public_error_sent"] is False


def test_pr321_combo_fail_prefers_delivered_job_over_same_key_failed_job(monkeypatch):
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *args, **kwargs: True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|combo_fail"] = {
        "job_key": "42|chat|video|combo_fail",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_percent": 5,
        "updated_at": time.time() + 10,
    }
    bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|combo_success"] = {
        "job_key": "42|chat|video|combo_success",
        "user_id": 42,
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "completed",
        "terminal_state": "delivered",
        "terminal_artifact_type": "video",
        "video_delivery_message_id": "901",
        "final_mp4_delivered": True,
        "updated_at": time.time(),
    }
    message = _Message()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            message,
            "42|chat|video|combo_fail",
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            reason="late_generic_error",
            lang="vi",
        )
    )

    assert result["suppressed"] is True
    assert message.texts == []
    job = bot.SUBTITLE_DUB_PIPELINE_JOBS["42|chat|video|combo_success"]
    assert job["late_fail_suppressed"] is True
    assert job["public_failure_sent"] is False


def test_pr321_no_product_video_music_payos_files_touched():
    # Scope guard for this hotfix: only SubDub terminal/delivery code and this test may change.
    import subprocess

    changed = {
        line.strip().replace("\\", "/")
        for line in subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True).splitlines()
        if line.strip()
    }

    assert changed <= {
        "bot.py",
        "tests/test_p0_19m_pr321_subdub_no_extra_srt_no_dub_fail.py",
    }
