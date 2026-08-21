from __future__ import annotations

import asyncio

import providers.key4u_provider as key4u_module
from providers.key4u_provider import Key4UConfig, Key4UProvider


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.content = b"json"
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class _AsyncClient:
    def __init__(self, responses, calls, **_kwargs):
        self.responses = responses
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, *, headers=None, json=None, **_kwargs):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return self.responses.pop(0)


def _provider(monkeypatch, responses, *, base_url="https://legacy.example/v1", model="legacy-model"):
    calls = []
    monkeypatch.setattr(
        key4u_module.httpx,
        "AsyncClient",
        lambda **kwargs: _AsyncClient(responses, calls, **kwargs),
    )
    provider = Key4UProvider(
        Key4UConfig(
            enabled=True,
            public_enabled=True,
            admin_smoke_enabled=True,
            api_key="sk-private-never-expose",
            base_url="https://legacy.example",
            openai_base_url=base_url,
            chat_model=model,
        )
    )
    return provider, calls


def test_key4u_public_openai_route_is_exact_model_exact_url_and_actual_usage(monkeypatch):
    provider, calls = _provider(
        monkeypatch,
        [_Response(200, {"choices": [{"message": {"content": "  answer  "}}], "usage": {"prompt_tokens": 11, "completion_tokens": 7}})],
    )

    result = asyncio.run(provider.public_chat_completion([{"role": "user", "content": "hello"}]))

    assert result["ok"] is True
    assert result["text"] == "answer"
    assert result["model"] == "claude-opus-4-8"
    assert result["usage"] == {
        "input_tokens": 11,
        "output_tokens": 7,
        "cache_read_tokens": 0,
        "input_tokens_include_cache": True,
    }
    assert calls[0]["url"] == "https://api.key4u.vn/v1/chat/completions"
    assert calls[0]["json"]["model"] == "claude-opus-4-8"
    assert len(calls) == 1


def test_key4u_public_anthropic_route_is_exact_and_requires_actual_usage(monkeypatch):
    provider, calls = _provider(
        monkeypatch,
        [_Response(200, {"content": [{"type": "text", "text": "anthropic answer"}], "usage": {"input_tokens": 5, "output_tokens": 9}})],
    )

    result = asyncio.run(provider.public_anthropic_messages([{"role": "user", "content": "hello"}]))

    assert result["ok"] is True
    assert result["usage"] == {
        "input_tokens": 5,
        "output_tokens": 9,
        "cache_read_tokens": 0,
        "input_tokens_include_cache": False,
    }
    assert calls[0]["url"] == "https://api.key4u.vn/v1/messages"
    assert calls[0]["json"]["model"] == "claude-opus-4-8"
    assert len(calls) == 1


def test_key4u_public_success_without_usage_is_invalid_and_does_not_retry(monkeypatch):
    provider, calls = _provider(
        monkeypatch,
        [_Response(200, {"choices": [{"message": {"content": "answer"}}]})],
    )

    result = asyncio.run(provider.public_chat_completion([{"role": "user", "content": "hello"}]))

    assert result["ok"] is False
    assert result["status"] == "FAIL_USAGE_REQUIRED"
    assert len(calls) == 1


def test_key4u_public_failure_has_no_fallback_and_no_secret_in_result(monkeypatch):
    provider, calls = _provider(
        monkeypatch,
        [_Response(503, {"error": "Bearer sk-private-never-expose provider unavailable"})],
    )

    result = asyncio.run(provider.public_chat_completion([{"role": "user", "content": "hello"}]))

    assert result["ok"] is False
    assert len(calls) == 1
    assert "sk-private-never-expose" not in str(result)


def test_existing_non_public_chat_completion_keeps_configured_route_and_model(monkeypatch):
    provider, calls = _provider(
        monkeypatch,
        [_Response(200, {"choices": [{"message": {"content": "legacy"}}]})],
        base_url="https://legacy.example/v1",
        model="legacy-model",
    )

    result = asyncio.run(provider.chat_completion("hello"))

    assert result["ok"] is True
    assert result["text"] == "legacy"
    assert calls[0]["url"] == "https://legacy.example/v1/chat/completions"
    assert calls[0]["json"]["model"] == "legacy-model"
