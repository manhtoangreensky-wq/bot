from __future__ import annotations

import pytest

from services.public_chat_media import (
    MediaInput,
    MediaValidationError,
    assess_video_readiness,
    validate_media_input,
    validate_text_output,
)


@pytest.mark.parametrize(
    ("kind", "mime_type", "filename"),
    [
        ("text", "text/plain", "note.txt"),
        ("image", "image/jpeg", "photo.jpg"),
        ("audio", "audio/mpeg", "voice.mp3"),
        ("video", "video/mp4", "clip.mp4"),
        ("pdf", "application/pdf", "brief.pdf"),
    ],
)
def test_public_chat_accepts_only_supported_input_families(kind, mime_type, filename):
    media = MediaInput(kind=kind, mime_type=mime_type, size_bytes=128, filename=filename)

    assert validate_media_input(media) == media


@pytest.mark.parametrize(
    "media",
    [
        MediaInput(kind="archive", mime_type="application/zip", size_bytes=128, filename="x.zip"),
        MediaInput(kind="image", mime_type="application/x-msdownload", size_bytes=128, filename="x.exe"),
        MediaInput(kind="pdf", mime_type="application/pdf", size_bytes=0, filename="empty.pdf"),
        MediaInput(kind="video", mime_type="video/mp4", size_bytes=101 * 1024 * 1024, filename="huge.mp4"),
    ],
)
def test_public_chat_rejects_unsupported_mismatched_empty_or_oversized_media(media):
    with pytest.raises(MediaValidationError):
        validate_media_input(media)


def test_public_chat_output_is_text_only_and_non_empty():
    assert validate_text_output("  final answer  ") == "final answer"

    for invalid in ("", "   ", b"bytes", {"text": "not a string"}, None):
        with pytest.raises(MediaValidationError):
            validate_text_output(invalid)


@pytest.mark.parametrize("state", ["PENDING", "PROCESSING", "READY", "SUCCEEDED", "UNKNOWN", ""])
def test_video_is_not_ready_until_state_is_exactly_active(state):
    readiness = assess_video_readiness(state)

    assert readiness.ready is False
    assert readiness.terminal_failure is False


@pytest.mark.parametrize("state", ["FAILED", "ERROR", "CANCELLED", "EXPIRED"])
def test_video_terminal_failure_is_not_retryable(state):
    readiness = assess_video_readiness(state)

    assert readiness.ready is False
    assert readiness.terminal_failure is True


def test_video_active_is_the_only_ready_state():
    readiness = assess_video_readiness("ACTIVE")

    assert readiness.ready is True
    assert readiness.terminal_failure is False
