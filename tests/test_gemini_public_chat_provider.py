from __future__ import annotations

import asyncio
from types import SimpleNamespace

from providers.gemini_public_chat_provider import GEMINI_PUBLIC_CHAT_MODEL, GeminiPublicChatProvider
from services.public_chat_media import MediaInput


class _Models:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _Files:
    def __init__(self, states):
        self.states = list(states)
        self.calls = []

    def get(self, *, name):
        self.calls.append(name)
        state = self.states.pop(0) if self.states else "UNKNOWN"
        return SimpleNamespace(name=name, state=state)


class _Client:
    def __init__(self, responses, states=()):
        self.models = _Models(responses)
        self.files = _Files(states)


def _response(text="hello", *, prompt_tokens=3, output_tokens=2):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens,
            candidates_token_count=output_tokens,
        ),
    )


def test_gemini_public_chat_uses_only_exact_model_and_returns_text_usage():
    client = _Client([_response("  xin chào  ")])
    provider = GeminiPublicChatProvider(client=client)

    result = asyncio.run(provider.generate("hello"))

    assert result == {
        "ok": True,
        "provider": "gemini",
        "model": GEMINI_PUBLIC_CHAT_MODEL,
        "text": "xin chào",
        "usage": {"input_tokens": 3, "output_tokens": 2},
        "status": "SUCCESS",
    }
    assert GEMINI_PUBLIC_CHAT_MODEL == "gemini-3.6-flash"
    assert [call["model"] for call in client.models.calls] == ["gemini-3.6-flash"]


def test_gemini_public_chat_empty_or_exception_has_no_fallback():
    for response in (_response("   "), RuntimeError("provider unavailable")):
        client = _Client([response])
        provider = GeminiPublicChatProvider(client=client)

        result = asyncio.run(provider.generate("hello"))

        assert result["ok"] is False
        assert result["text"] == ""
        assert len(client.models.calls) == 1
        assert "provider unavailable" not in str(result)


def test_gemini_video_waits_for_exact_active_before_generation():
    client = _Client([_response("video summary")], states=["PENDING", "PROCESSING", "ACTIVE"])
    provider = GeminiPublicChatProvider(client=client, sleep=lambda _seconds: None)
    video = MediaInput(
        kind="video",
        mime_type="video/mp4",
        size_bytes=1024,
        filename="clip.mp4",
        provider_file_name="files/video-1",
    )

    result = asyncio.run(provider.generate("summarize", media=[video], video_poll_interval=0, video_max_polls=3))

    assert result["ok"] is True
    assert client.files.calls == ["files/video-1", "files/video-1", "files/video-1"]
    assert len(client.models.calls) == 1


def test_gemini_ready_succeeded_and_unknown_are_never_treated_as_video_ready():
    for state in ("READY", "SUCCEEDED", "UNKNOWN"):
        client = _Client([_response("must not run")], states=[state])
        provider = GeminiPublicChatProvider(client=client, sleep=lambda _seconds: None)
        video = MediaInput("video", "video/mp4", 10, "clip.mp4", "files/video-1")

        result = asyncio.run(provider.generate("summarize", media=[video], video_poll_interval=0, video_max_polls=1))

        assert result["ok"] is False
        assert result["status"] == "VIDEO_NOT_ACTIVE"
        assert client.models.calls == []


def test_gemini_terminal_video_failure_stops_without_generation():
    client = _Client([_response("must not run")], states=["FAILED", "ACTIVE"])
    provider = GeminiPublicChatProvider(client=client, sleep=lambda _seconds: None)
    video = MediaInput("video", "video/mp4", 10, "clip.mp4", "files/video-1")

    result = asyncio.run(provider.generate("summarize", media=[video], video_poll_interval=0, video_max_polls=2))

    assert result["ok"] is False
    assert result["status"] == "VIDEO_FAILED"
    assert client.files.calls == ["files/video-1"]
    assert client.models.calls == []
