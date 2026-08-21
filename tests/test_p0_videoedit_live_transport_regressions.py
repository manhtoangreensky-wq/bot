from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace

import pytest
from PIL import Image

import bot


@pytest.mark.parametrize(
    "event_payload",
    [
        {
            "message": {
                "message_id": 73,
                "chat": {"id": 7_126_457_028},
                "text": "/video",
            }
        },
        {
            "callback_query": {
                "id": "same-telegram-callback",
                "from": {"id": 7_126_457_028},
                "data": "videoedit|cut",
                "message": {
                    "message_id": 74,
                    "chat": {"id": 7_126_457_028},
                },
            }
        },
    ],
    ids=("message", "callback"),
)
def test_dual_cloud_and_local_webhooks_process_one_telegram_event_once(
    monkeypatch,
    event_payload: dict,
) -> None:
    calls: list[object] = []

    class App:
        async def process_update(self, update):
            calls.append(update)

    monkeypatch.setattr(bot, "tg_app", App())
    bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
    bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()
    first = {"update_id": 101, **event_payload}
    forwarded = {"update_id": 9_001, **event_payload}

    try:
        asyncio.run(bot.process_telegram_update_once(SimpleNamespace(), first))
        asyncio.run(bot.process_telegram_update_once(SimpleNamespace(), forwarded))
    finally:
        bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
        bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()

    assert len(calls) == 1


def test_stable_webhook_dedupe_keeps_distinct_telegram_events(monkeypatch) -> None:
    calls: list[object] = []

    class App:
        async def process_update(self, update):
            calls.append(update)

    monkeypatch.setattr(bot, "tg_app", App())
    bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
    bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()
    payloads = [
        {
            "update_id": 201,
            "message": {"message_id": 80, "chat": {"id": 1}, "text": "/start"},
        },
        {
            "update_id": 202,
            "message": {"message_id": 81, "chat": {"id": 1}, "text": "/video"},
        },
        {
            "update_id": 203,
            "message": {"message_id": 80, "chat": {"id": 2}, "text": "/start"},
        },
        {
            "update_id": 204,
            "callback_query": {"id": "callback-a", "data": "videoedit|cut"},
        },
        {
            "update_id": 205,
            "callback_query": {"id": "callback-b", "data": "videoedit|cut"},
        },
    ]

    try:
        for payload in payloads:
            asyncio.run(bot.process_telegram_update_once(SimpleNamespace(), payload))
    finally:
        bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
        bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()

    assert len(calls) == len(payloads)


def test_stable_webhook_dedupe_keeps_distinct_edited_message_revisions(
    monkeypatch,
) -> None:
    calls: list[object] = []

    class App:
        async def process_update(self, update):
            calls.append(update)

    monkeypatch.setattr(bot, "tg_app", App())
    bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
    bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()
    first_revision = {
        "edited_message": {
            "message_id": 90,
            "chat": {"id": 1},
            "edit_date": 1_786_300_001,
            "text": "first revision",
        }
    }
    second_revision = {
        "edited_message": {
            "message_id": 90,
            "chat": {"id": 1},
            "edit_date": 1_786_300_002,
            "text": "second revision",
        }
    }

    try:
        asyncio.run(
            bot.process_telegram_update_once(
                SimpleNamespace(), {"update_id": 301, **first_revision}
            )
        )
        asyncio.run(
            bot.process_telegram_update_once(
                SimpleNamespace(), {"update_id": 9_301, **first_revision}
            )
        )
        asyncio.run(
            bot.process_telegram_update_once(
                SimpleNamespace(), {"update_id": 302, **second_revision}
            )
        )
    finally:
        bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
        bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()

    assert len(calls) == 2


def test_stable_webhook_dedupe_keeps_business_connections_distinct(
    monkeypatch,
) -> None:
    calls: list[object] = []

    class App:
        async def process_update(self, update):
            calls.append(update)

    monkeypatch.setattr(bot, "tg_app", App())
    bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
    bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()
    payloads = [
        {
            "update_id": 401,
            "business_message": {
                "business_connection_id": "business-a",
                "message_id": 91,
                "chat": {"id": 1},
                "text": "hello",
            },
        },
        {
            "update_id": 402,
            "business_message": {
                "business_connection_id": "business-b",
                "message_id": 91,
                "chat": {"id": 1},
                "text": "hello",
            },
        },
    ]

    try:
        for payload in payloads:
            asyncio.run(bot.process_telegram_update_once(SimpleNamespace(), payload))
    finally:
        bot.TELEGRAM_UPDATE_DEDUPE_DONE.clear()
        bot.TELEGRAM_UPDATE_DEDUPE_LOCKS.clear()

    assert len(calls) == len(payloads)


def test_logo_validation_fetches_local_bot_api_media_over_https(monkeypatch) -> None:
    payload = io.BytesIO()
    Image.new("RGBA", (200, 100), (20, 120, 220, 255)).save(payload, format="PNG")
    png_bytes = payload.getvalue()
    drive_download_called = False

    class TelegramFile:
        file_path = "/var/lib/telegram-bot-api/token/photos/file_0"
        file_size = len(png_bytes)

        async def download_to_drive(self, *, custom_path):
            nonlocal drive_download_called
            drive_download_called = True
            raise FileNotFoundError(custom_path)

    class TelegramBot:
        async def get_file(self, _file_id):
            return TelegramFile()

    async def fetch_local_media(url: str, maximum_bytes: int, read_timeout: float):
        assert url == "https://tg.toanaas.invalid/localfile/token/photos/file_0"
        assert maximum_bytes == bot.video_local_validation.MAX_LOGO_BYTES
        assert read_timeout > 0
        return png_bytes

    monkeypatch.setattr(
        bot,
        "telegram_local_media_url",
        lambda _path: "https://tg.toanaas.invalid/localfile/token/photos/file_0",
    )
    monkeypatch.setattr(bot, "telegram_local_media_fetch", fetch_local_media)

    result = asyncio.run(
        bot.inspect_video_editor_logo(
            SimpleNamespace(bot=TelegramBot()),
            {
                "file_id": "logo-file-id",
                "file_name": "logo.png",
                "file_size": len(png_bytes),
            },
        )
    )

    assert result["ok"] is True
    assert result["format"] == "png"
    assert result["width"] == 200
    assert result["height"] == 100
    assert drive_download_called is False
