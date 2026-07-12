import asyncio
from types import SimpleNamespace

import pytest

import bot


class _TelegramFile:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def download_as_bytearray(self):
        return bytearray(self.payload)


class _TelegramBot:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.file_ids = []

    async def get_file(self, file_id):
        self.file_ids.append(file_id)
        return _TelegramFile(self.payload)


def _state(duration: int) -> dict:
    return {
        "video_file_id": "telegram-video",
        "video_file_size": 1024,
        "video_duration": duration,
        "source_mime_type": "video/mp4",
        "source_file_name": "long.mp4",
    }


def test_long_root_input_reaches_project_splitter_instead_of_300s_download_block():
    context = SimpleNamespace(bot=_TelegramBot(b"fixture-video"))

    payload, content_type = asyncio.run(
        bot.video_dubbing_download_source(context, _state(500))
    )
    gate = bot.subdub_duration_gate_payload({"duration": 500}, _state(500))
    project = bot.subdub_long_project_plan(500)

    assert payload == b"fixture-video"
    assert content_type == "video/mp4"
    assert context.bot.file_ids == ["telegram-video"]
    assert gate["duration_gate_result"] == "fail_over_limit"
    assert project["project_supported"] is True
    assert project["project_part_count"] == 2


def test_input_beyond_long_project_limit_is_blocked_before_download():
    context = SimpleNamespace(bot=_TelegramBot(b"must-not-download"))

    with pytest.raises(RuntimeError, match="video_too_large"):
        asyncio.run(
            bot.video_dubbing_download_source(
                context,
                _state(bot.SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS + 1),
            )
        )

    assert context.bot.file_ids == []


def test_31s_and_60s_inputs_keep_the_chunked_asr_route():
    for duration, expected_chunks in ((31, 2), (60, 2)):
        gate = bot.subdub_duration_gate_payload({"duration": duration}, _state(duration))
        assert gate["duration_gate_result"] == "pass_long"
        assert gate["chunking_enabled"] is True
        assert gate["chunk_count"] == expected_chunks
        assert gate["chunk_strategy"] == "asr_audio_chunks"

