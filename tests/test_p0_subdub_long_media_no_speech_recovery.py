import asyncio

from services import subdub_long_media


def _ranges(count=3):
    return [
        {"index": index, "start": (index - 1) * 30.0, "end": index * 30.0}
        for index in range(1, count + 1)
    ]


def test_long_media_skips_no_speech_chunk_and_keeps_absolute_timestamps():
    transcribe_calls = []

    async def extract_chunk(_source, _content_type, start, duration):
        return f"chunk-{int(start)}".encode(), "audio/mpeg", f"fixture:{start}:{duration}"

    async def transcribe_chunk(audio, _content_type):
        transcribe_calls.append(audio)
        if audio == b"chunk-0":
            return {
                "ok": False,
                "status": "deepgram_empty_transcript",
                "text": "",
                "detail": "no speech in this range",
            }
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture-asr",
            "text": "later speech",
            "segments": [{"start": 1.0, "end": 3.0, "text": "later speech"}],
            "language": "en",
        }

    result = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            _ranges(2),
            extract_chunk=extract_chunk,
            transcribe_chunk=transcribe_chunk,
            input_duration_seconds=60,
        )
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["skipped_chunk_count"] == 1
    assert result["skipped_chunk_indices"] == [1]
    assert result["speech_chunk_count"] == 1
    assert [(cue["start"], cue["end"]) for cue in result["segments"]] == [(31.0, 33.0)]
    assert result["global_timing_preserved"] is True
    assert transcribe_calls == [b"chunk-0", b"chunk-30"]


def test_long_media_all_no_speech_is_truthful_terminal_failure():
    async def extract_chunk(_source, _content_type, start, duration):
        return b"silence", "audio/mpeg", f"fixture:{start}:{duration}"

    async def transcribe_chunk(_audio, _content_type):
        return {
            "ok": False,
            "status": "empty_transcript",
            "text": "",
            "no_speech": True,
        }

    result = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            _ranges(2),
            extract_chunk=extract_chunk,
            transcribe_chunk=transcribe_chunk,
            input_duration_seconds=60,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "long_media_no_speech"
    assert result["segments"] == []
    assert result["text"] == ""
    assert result["skipped_chunk_count"] == 2
    assert result["skipped_chunk_indices"] == [1, 2]
    assert result["speech_chunk_count"] == 0


def test_long_media_provider_error_remains_terminal_and_is_not_skipped():
    async def extract_chunk(_source, _content_type, start, duration):
        return f"chunk-{int(start)}".encode(), "audio/mpeg", "fixture"

    async def transcribe_chunk(audio, _content_type):
        if audio == b"chunk-0":
            return {
                "ok": False,
                "status": "deepgram_empty_transcript",
                "text": "",
            }
        return {
            "ok": False,
            "status": "deepgram_http_503",
            "detail": "provider unavailable",
            "text": "",
        }

    result = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            _ranges(2),
            extract_chunk=extract_chunk,
            transcribe_chunk=transcribe_chunk,
            input_duration_seconds=60,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "deepgram_http_503"
    assert result["failed_chunk_index"] == 2
    assert result["skipped_chunk_count"] == 1
    assert result["skipped_chunk_indices"] == [1]


def test_long_media_network_exception_remains_terminal():
    async def extract_chunk(_source, _content_type, _start, _duration):
        return b"speech", "audio/mpeg", "fixture"

    async def transcribe_chunk(_audio, _content_type):
        raise TimeoutError("provider timeout")

    result = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            _ranges(1),
            extract_chunk=extract_chunk,
            transcribe_chunk=transcribe_chunk,
            input_duration_seconds=30,
        )
    )

    assert result["ok"] is False
    assert result["status"] == "ACCEPTANCE_UNKNOWN"
    assert "provider_acceptance_unknown" in result["detail"]
    assert result["failed_chunk_index"] == 1
