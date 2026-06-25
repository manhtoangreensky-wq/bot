import asyncio
import inspect
import json
import os
from types import SimpleNamespace

import bot


class CaptureMessage:
    def __init__(self):
        self.outputs = []
        self.chat_id = 175500

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"document": document, "filename": filename, "caption": str(caption or ""), **kwargs})

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})

    async def reply_video(self, video=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"video": video, "filename": filename, "caption": str(caption or ""), **kwargs})


def test_pipeline_limits_replace_legacy_15mb_default():
    assert bot.PIPELINE_MAX_INPUT_MB_ADMIN == 100
    assert bot.PIPELINE_MAX_INPUT_MB_PUBLIC == 50
    assert bot.PIPELINE_MAX_DURATION_SECONDS_ADMIN == 180
    assert bot.PIPELINE_MAX_DURATION_SECONDS_PUBLIC == 90


def test_admin_smoke_allows_over_15mb_under_admin_limit(monkeypatch, tmp_path):
    class TelegramFile:
        async def download_to_drive(self, custom_path):
            with open(custom_path, "wb") as handle:
                handle.write(b"streamed")

    class Media:
        file_id = "file"
        file_unique_id = "unique"
        file_name = "sample.mp4"
        mime_type = "video/mp4"
        file_size = 16 * 1024 * 1024
        duration = 30

        async def get_file(self):
            return TelegramFile()

    message = SimpleNamespace(reply_to_message=SimpleNamespace(video=Media(), audio=None, voice=None, document=None))
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=1))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    result = asyncio.run(bot.resolve_stt_test_media(update, SimpleNamespace()))

    assert result["bytes"] == b"streamed"
    assert result["download_mode"] == "stream_path"


def test_public_limit_clean_guard_skips_download(monkeypatch):
    calls = {"download": 0}

    class TelegramFile:
        async def download_to_drive(self, custom_path):
            calls["download"] += 1

    class Media:
        file_id = "file"
        file_unique_id = "unique"
        file_name = "sample.mp4"
        mime_type = "video/mp4"
        file_size = 51 * 1024 * 1024
        duration = 30

        async def get_file(self):
            return TelegramFile()

    message = SimpleNamespace(reply_to_message=SimpleNamespace(video=Media(), audio=None, voice=None, document=None))
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=2))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)

    result = asyncio.run(bot.resolve_stt_test_media(update, SimpleNamespace()))

    assert result["error"] == "input_too_large"
    assert calls["download"] == 0


def test_same_full_dub_job_deduped():
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    key = bot.subtitle_dub_pipeline_job_key(1, 2, "file", "unique", bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "smoke")
    first, job = bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=2)
    second, duplicate = bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=2)

    assert first is True
    assert second is False
    assert duplicate["job_id"] == job["job_id"]
    assert duplicate["duplicate_count"] == 1


def test_output_sent_once():
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    key = "output-once"
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)

    assert bot.mark_subtitle_dub_pipeline_output_sent(key) is True
    assert bot.mark_subtitle_dub_pipeline_output_sent(key) is False


def test_cancel_pipeline_sets_cancelled():
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    key = "cancel-me"
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=10, chat_id=20)

    assert bot.cancel_subtitle_dub_pipeline_jobs(10, 20) == 1
    assert bot.subtitle_dub_pipeline_cancelled(key) is True
    assert bot.get_subtitle_dub_pipeline_job(key)["status"] == "cancelled"


def test_cancelled_pipeline_stops_before_next_send():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert source.rfind("subtitle_dub_pipeline_cancelled") < source.index("send_public_subtitle_dub_final_outputs")


def test_pipeline_workspace_manifest_and_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "PIPELINE_TEMP_ROOT", str(tmp_path / "tmp" / "toan_aas_pipeline"))
    workspace = bot.create_subtitle_dub_pipeline_workspace("job-1")
    info = bot.record_subtitle_dub_pipeline_workspace_outputs(
        workspace,
        {
            "original_srt": "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            "translated_srt": "1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
            "dub_audio_raw": b"raw",
            "dub_audio": b"normalized",
            "final_video": b"mp4",
            "mux_status": "completed",
        },
        source_bytes=b"source",
        source_content_type="video/mp4",
        target_language="vi",
        include_source=True,
    )

    assert os.path.exists(info["manifest_path"])
    manifest = json.loads(open(info["manifest_path"], encoding="utf-8").read())
    assert manifest["outputs"]["dub_audio_normalized"]["bytes"] == len(b"normalized")
    assert manifest["outputs"]["final_video"]["bytes"] == 3
    assert bot.cleanup_subtitle_dub_pipeline_workspace(workspace) is True
    assert not os.path.exists(workspace)


def test_public_full_dub_sends_final_mp4_only_when_mux_ready():
    message = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        subtitle_items=[{"bytes": b"srt", "filename": "x.srt"}],
        srt_text="subtitle",
        audio_bytes=b"audio",
        video_bytes=b"mp4",
    ))

    assert result == {"documents": 0, "audio": 0, "video": 1}
    assert len(message.outputs) == 1
    assert message.outputs[0]["filename"].endswith(".mp4")


def test_public_full_dub_mux_unavailable_sends_audio_and_one_subtitle():
    message = CaptureMessage()
    result = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        srt_text="1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
        audio_bytes=b"audio",
        video_bytes=b"",
    ))

    assert result == {"documents": 1, "audio": 1, "video": 0}
    assert len([item for item in message.outputs if item.get("document")]) == 1
    assert len([item for item in message.outputs if item.get("audio")]) == 1
    assert any("Ghép video đang tạm chưa sẵn sàng" in item.get("text", "") for item in message.outputs)


def test_admin_smoke_default_not_spam_files():
    message = CaptureMessage()
    result = asyncio.run(bot.send_admin_full_dub_final_outputs(
        message,
        {
            "original_srt": "original",
            "translated_srt": "translated",
            "dub_audio": b"audio",
            "final_video": b"",
        },
        "vi",
        debug_output=False,
    ))

    assert result["original_sent"] == 0
    assert result["translated_sent"] == 1
    assert len([item for item in message.outputs if item.get("document")]) == 1
    assert len([item for item in message.outputs if item.get("audio")]) == 1


def test_admin_smoke_debug_output_sends_intermediate_files():
    message = CaptureMessage()
    result = asyncio.run(bot.send_admin_full_dub_final_outputs(
        message,
        {
            "original_srt": "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            "translated_srt": "1\n00:00:00,000 --> 00:00:01,000\nXin chao\n",
            "dub_audio": b"audio",
            "final_video": b"",
        },
        "vi",
        debug_output=True,
    ))

    assert result["original_sent"] == 3
    assert result["translated_sent"] == 3
    assert len([item for item in message.outputs if item.get("document")]) == 6


def test_admin_target_same_no_translation():
    assert bot.admin_full_dub_video_target_language(["--confirm-paid", "--target", "same"]) == "same"
    assert bot.admin_full_dub_video_target_language(["--confirm-paid", "--target=vi"]) == "vi"


def test_public_language_choice_includes_keep_original():
    labels = [button.text for row in bot.video_dubbing_language_keyboard(
        "vi",
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB},
    ).inline_keyboard for button in row]
    assert any("Giữ nguyên ngôn ngữ gốc" in label for label in labels)


def test_public_can_request_all_files_after_completion(monkeypatch, tmp_path):
    subtitle_path = tmp_path / "subtitle.srt"
    audio_path = tmp_path / "audio.mp3"
    subtitle_path.write_bytes(b"subtitle")
    audio_path.write_bytes(b"audio")
    bot.remember_subtitle_dub_pipeline_result(
        77,
        subtitle_asset_ids=["sub-1"],
        translation_asset_ids=[],
        dub_asset_id="dub-1",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "get_translation_asset_record", lambda _asset: {})
    monkeypatch.setattr(bot, "get_subtitle_asset_record", lambda _asset: {"local_path": str(subtitle_path)})
    monkeypatch.setattr(bot, "get_dub_asset_record", lambda _asset: {"local_path": str(audio_path)})

    class Query:
        data = "videodub|job_download|all"
        from_user = SimpleNamespace(id=77)
        message = CaptureMessage()

        async def answer(self, *args, **kwargs):
            return None

    asyncio.run(bot.handle_video_dubbing_callback(
        SimpleNamespace(callback_query=Query()),
        SimpleNamespace(),
    ))

    assert len([item for item in Query.message.outputs if item.get("document")]) == 1
    assert len([item for item in Query.message.outputs if item.get("audio")]) == 1


def test_mux_ready_requires_flag_and_ffmpeg(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_DUB_MUX_ENABLED", False)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    assert bot.video_dub_mux_ready() is False
    monkeypatch.setattr(bot, "VIDEO_DUB_MUX_ENABLED", True)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "")
    assert bot.video_dub_mux_ready() is False
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    assert bot.video_dub_mux_ready() is True


def test_dub_audio_gain_fallback_when_loudnorm_unavailable(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "DUB_AUDIO_NORMALIZE_ENABLED", True)
    monkeypatch.setattr(bot, "DUB_AUDIO_FALLBACK_GAIN_DB", 99)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def fake_run(command, timeout=0):
        calls.append(command)
        if len(calls) == 1:
            return False, "loudnorm unavailable"
        with open(command[-1], "wb") as handle:
            handle.write(b"normalized")
        return True, "ok"

    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    audio, detail = asyncio.run(bot.normalize_dub_audio_bytes(b"raw-audio"))

    assert audio == b"normalized"
    assert detail == "ffmpeg_gain_fallback"
    assert "volume=12.0dB,alimiter=limit=0.95" in calls[1]


def test_mixed_video_original_audio_lowered(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "ORIGINAL_AUDIO_MIX_VOLUME", 0.15)
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")

    async def fake_run(command, timeout=0):
        calls.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"mp4")
        return True, "ok"

    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    output, detail = asyncio.run(bot.video_dubbing_render_video(
        b"video",
        dubbed_audio=b"audio",
        keep_original_audio=True,
    ))

    assert output == b"mp4"
    assert detail == "ffmpeg_video_render"
    assert any("volume=0.150" in part and "alimiter=limit=0.95" in part for part in calls[0])


def test_cancel_command_returns_clean_message(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.acquire_subtitle_dub_pipeline_job("cancel-command", user_id=55, chat_id=55)
    message = CaptureMessage()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=55),
        effective_chat=SimpleNamespace(id=55),
        message=message,
    )

    asyncio.run(bot.cmd_cancel_pipeline(update, SimpleNamespace()))

    assert "Đã hủy tác vụ pipeline" in message.outputs[-1]["text"]
