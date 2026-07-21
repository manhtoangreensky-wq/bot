import asyncio
import inspect
import os
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self):
        self.calls = []
        self.chat_id = 12345

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return SimpleNamespace(message_id=len(self.calls), video=SimpleNamespace(file_id=f"video-{len(self.calls)}"))

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=len(self.calls), document=SimpleNamespace(file_id=f"document-{len(self.calls)}"))

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=len(self.calls), audio=SimpleNamespace(file_id=f"audio-{len(self.calls)}"))

    async def reply_text(self, text, **kwargs):
        self.calls.append(("text", {"text": text, **kwargs}))
        return SimpleNamespace(message_id=len(self.calls))


def _saved_input(tmp_path, *, duration=2, size=1024, content_type="video/mp4"):
    path = tmp_path / "input.mp4"
    path.write_bytes(b"x" * max(0, int(size)))
    return {
        "ok": True,
        "path": str(path),
        "exists": True,
        "file_saved": True,
        "size": int(size),
        "duration": int(duration),
        "content_type": content_type,
        "file_id": "tg-video",
    }


def _job_key(name):
    return f"p019j|{name}"


def test_subtitle_only_accepts_telegram_video_and_creates_job(tmp_path):
    input_save = _saved_input(tmp_path, duration=3)
    validation = bot.subdub_validate_saved_input_for_pipeline(input_save, {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE})
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(_job_key("subtitle-intake"), user_id=1, chat_id=1)

    assert validation["ok"] is True
    assert acquired is True
    assert job["status"] == "running"


def test_subtitle_only_does_not_drop_session_after_video_upload():
    uid = 190190
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(uid, "await_video", mode=bot.VIDEO_SUBTITLE_MODE_CREATE, active_flow="subtitle_only")
    state = bot.set_video_dubbing_pending(uid, "source", video_file_id="tg-video", source_duration="3")

    assert state["video_file_id"] == "tg-video"
    assert state["mode"] == bot.VIDEO_SUBTITLE_MODE_CREATE
    assert bot.get_video_dubbing_pending(uid)["source_duration"] == "3"


def test_subtitle_only_rejects_missing_input_with_clean_no_charge(tmp_path):
    validation = bot.subdub_validate_saved_input_for_pipeline({"ok": True, "path": str(tmp_path / "missing.mp4"), "size": 0, "duration": 0, "content_type": "video/mp4"})
    text = bot.subdub_clean_failure_text("vi")

    assert validation["ok"] is False
    assert validation["blocker"] == "input_missing"
    assert "chưa trừ Xu" in text


def test_subtitle_only_valid_input_advances_past_10_percent(tmp_path):
    assert bot.subdub_validate_saved_input_for_pipeline(_saved_input(tmp_path))["ok"] is True
    assert bot.subdub_progress_stage_payload("speech_recognized")["percent"] > 10


def test_dub_only_requires_real_input_video(tmp_path):
    validation = bot.subdub_validate_saved_input_for_pipeline({"ok": True, "path": "", "size": 0, "duration": 0, "content_type": "video/mp4"})

    assert validation["ok"] is False
    assert validation["blocker"] == "input_missing"


def test_dub_only_requires_generated_dub_audio_before_success():
    terminal = bot.subdub_result_terminal_state({"ok": False, "status": "DUB_AUDIO_NOT_GENERATED"})

    assert terminal == "failed_no_charge"


def test_dub_only_output_must_have_duration_gt_zero(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 0.0, "has_video": True, "has_audio": True, "size": 2048}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    result = asyncio.run(bot.subdub_validate_video_output(b"video" * 600, require_audio=True, min_bytes=16))

    assert result["ok"] is False
    assert result["detail"] == "video_duration_zero"


def test_dub_only_output_must_have_audio_stream(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": False, "size": 2048}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    result = asyncio.run(bot.subdub_validate_video_output(b"video" * 600, require_audio=True, min_bytes=16))

    assert result["ok"] is False
    assert result["detail"] == "audio_stream_missing"


def test_subtitle_dub_uses_real_subdub_core_not_placeholder():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "placeholder" not in source.lower()


def test_subtitle_dub_requires_valid_mp4_before_delivery(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": False, "detail": "output_zero_duration", "duration": 0, "has_video": True, "has_audio": True}

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"audio",
        video_bytes=b"bad-video",
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video"] == 0
    assert sent["output_validation"]["ok"] is False
    assert sent["audio"] == 0
    assert sent["partial_audio_available"] is True
    assert sent["partial_audio_delivered"] is False
    assert sent["audio_fallback_suppressed"] is True
    assert sent["audio_artifact_internal_only"] is True
    assert sent["success_blocked_reason"] == "missing_valid_delivered_mp4"
    assert [kind for kind, _kwargs in message.calls] == []


def test_subtitle_dub_success_only_after_artifact_validation(monkeypatch):
    async def fake_validate(*_args, **_kwargs):
        return {"ok": True, "detail": "ok", "duration": 2.0, "has_video": True, "has_audio": True, "size": 2048}

    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        audio_bytes=b"audio",
        video_bytes=b"good-video" * 200,
        include_subtitle_outputs=False,
        strict_validation=True,
    ))

    assert sent["video"] == 1
    assert sent["output_validation"]["ok"] is True


def test_no_fail_then_success_same_job():
    key = _job_key("fail-then-success")
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)
    bot.update_subtitle_dub_pipeline_job(key, status="failed", terminal_state="failed_no_charge")

    assert bot.mark_subtitle_dub_pipeline_output_sent(key) is False
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == "failed_no_charge"


def test_failed_terminal_blocks_late_delivery():
    assert bot.subdub_terminal_state_allows_transition("failed_no_charge", "delivered") is False
    assert bot.subdub_terminal_blocks_late_delivery({"terminal_state": "failed_refunded"}) is True


def test_delivered_terminal_blocks_late_error():
    key = _job_key("delivered-late-error")
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)
    bot.mark_subtitle_dub_pipeline_output_sent(key)
    bot.update_subtitle_dub_pipeline_job(key, status="failed", terminal_state="failed_no_charge")

    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["terminal_state"] == "delivered"


def test_subdub_video_sent_once():
    key = _job_key("sent-once")
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)

    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is True
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered") is False


def test_subdub_success_sent_once():
    key = _job_key("success-once")
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="m1")

    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["subdub_success_message_id"] == "m1"
    assert bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", success_message_id="m2") is False


def test_update_status_does_not_reprocess():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    branch = source[source.find('if action == "subdub_status"'):source.find('if action == "type"', source.find('if action == "subdub_status"'))]

    assert "subdub_job_public_status_text" in branch
    assert "execute_video_dubbing_pipeline" not in branch


def test_debug_commands_are_read_only():
    combined = "\n".join(inspect.getsource(func) for func in (
        bot.cmd_subdub_job_debug,
        bot.cmd_subdub_render_debug,
        bot.cmd_subdub_delivery_debug,
        bot.cmd_subdub_voice_debug,
    ))

    assert "execute_video_dubbing_pipeline" not in combined
    assert "send_public_subtitle_dub_final_outputs" not in combined


def test_zero_duration_output_not_delivered(monkeypatch):
    async def fake_probe(_video_bytes):
        return {"ok": True, "detail": "ok", "duration": 0.0, "has_video": True, "has_audio": True, "size": 2048}

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    assert asyncio.run(bot.subdub_validate_video_output(b"x" * 2048, require_audio=True, min_bytes=16))["ok"] is False


def test_empty_output_not_delivered():
    assert asyncio.run(bot.subdub_validate_video_output(b"", min_bytes=16))["ok"] is False


def test_missing_output_not_success():
    result = asyncio.run(bot.subdub_validate_video_output(None, min_bytes=16))

    assert result["ok"] is False
    assert result["detail"] == "video_too_small"


def test_black_empty_placeholder_not_success():
    result = bot.subdub_basic_mp4_validation(b"\x00\x00\x00\x18ftypmp42", min_bytes=512)

    assert result["ok"] is False


def test_progress_reaches_100_only_after_delivery():
    assert bot.subdub_progress_stage_payload("validating_output")["percent"] == 90
    assert bot.subdub_progress_stage_payload("delivered")["percent"] == 100


def test_progress_does_not_jump_from_10_to_public_fail_for_valid_input(tmp_path):
    validation = bot.subdub_validate_saved_input_for_pipeline(_saved_input(tmp_path, duration=4))

    assert validation["ok"] is True
    assert bot.subdub_progress_stage_payload("extracted_audio")["percent"] == 25


def test_progress_status_debug_is_read_only():
    source = inspect.getsource(bot.cmd_progress_status_debug)

    assert "execute_video_dubbing_pipeline" not in source
    assert "send_public_subtitle_dub_final_outputs" not in source
