import asyncio
import inspect
from types import SimpleNamespace

import bot


class DeliveryMessage:
    def __init__(self, *, message_id=True):
        self.calls = []
        self._message_id = message_id

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        if not self._message_id:
            return SimpleNamespace()
        return SimpleNamespace(message_id=101, video=SimpleNamespace(file_id="video-file-id"))

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        if not self._message_id:
            return SimpleNamespace()
        return SimpleNamespace(message_id=202, document=SimpleNamespace(file_id="document-file-id"))

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=303, audio=SimpleNamespace(file_id="audio-file-id"))


async def _valid_video(*_args, **_kwargs):
    return {"ok": True, "duration": 12.0, "has_video": True, "has_audio": True, "detail": "ok"}


def _set_limits(monkeypatch, *, preview=45, document=80, generated=80):
    monkeypatch.setattr(bot, "TELEGRAM_VIDEO_PREVIEW_MAX_MB", preview)
    monkeypatch.setattr(bot, "TELEGRAM_DOCUMENT_MAX_MB", document)
    monkeypatch.setattr(bot, "GENERATED_MEDIA_MAX_MB", generated)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", preview)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", document)
    monkeypatch.setattr(bot, "SUBDUB_ENABLE_DOCUMENT_FALLBACK", True)
    monkeypatch.setattr(bot, "subdub_validate_video_output", _valid_video)


def test_small_video_sent_as_video(monkeypatch):
    _set_limits(monkeypatch, preview=45, document=80, generated=80)
    message = DeliveryMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_bytes=b"small-real-mp4",
        strict_validation=True,
    ))

    assert [kind for kind, _ in message.calls] == ["video"]
    assert sent["video"] == 1
    assert sent["delivery_method"] == "video"
    assert sent["telegram_message_id"] == "101"


def test_large_video_sent_as_document(monkeypatch):
    _set_limits(monkeypatch, preview=1, document=3, generated=3)
    message = DeliveryMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_bytes=b"x" * (2 * 1024 * 1024),
        strict_validation=True,
    ))

    assert [kind for kind, _ in message.calls] == ["document"]
    assert sent["video_document"] == 1
    assert sent["delivery_method"] == "document"
    assert sent["telegram_message_id"] == "202"
    assert "File hơi lớn nên TOAN AAS gửi dưới dạng tệp" in message.calls[0][1]["caption"]


def test_delivery_success_requires_message_id(monkeypatch):
    _set_limits(monkeypatch, preview=45, document=80, generated=80)
    message = DeliveryMessage(message_id=False)

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_bytes=b"small-real-mp4",
        strict_validation=True,
    ))

    assert [kind for kind, _ in message.calls] == ["video"]
    assert sent["video"] == 0
    assert sent["delivery_method"] == "failed"
    assert sent["telegram_message_id"] == ""


def test_oversized_video_clean_fail(monkeypatch):
    _set_limits(monkeypatch, preview=1, document=2, generated=2)

    async def no_compress(*_args, **_kwargs):
        return b"", "compression_disabled"

    monkeypatch.setattr(bot, "subdub_compress_video_bytes", no_compress)
    message = DeliveryMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_bytes=b"x" * (3 * 1024 * 1024),
        strict_validation=True,
    ))

    assert message.calls == []
    assert sent["video"] == 0
    assert sent["video_document"] == 0
    assert sent.get("delivery_reason") in {"generated_media_too_large", "telegram_document_limit_exceeded"}


def test_no_15mb_hardcoded_limit():
    source = "\n".join([
        inspect.getsource(bot.generated_media_delivery_limits),
        inspect.getsource(bot.send_generated_video_bytes_for_delivery),
        inspect.getsource(bot.send_public_subtitle_dub_final_outputs),
    ])

    assert "15 * 1024 * 1024" not in source
    assert "TELEGRAM_VIDEO_PREVIEW_MAX_MB" in source
    assert "TELEGRAM_DOCUMENT_MAX_MB" in source
    assert "GENERATED_MEDIA_MAX_MB" in source


def test_delivery_debug_has_size_method(monkeypatch):
    _set_limits(monkeypatch, preview=1, document=3, generated=3)
    message = DeliveryMessage()

    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(
        message,
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_bytes=b"x" * (2 * 1024 * 1024),
        strict_validation=True,
    ))

    assert sent["delivery_method"] == "document"
    assert sent["file_size_mb"] == 2.0
    assert sent["size_limit_used"] == 3.0
    assert sent["telegram_message_id"] == "202"
