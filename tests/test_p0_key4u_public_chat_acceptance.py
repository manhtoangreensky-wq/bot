import asyncio
import base64

import httpx
import pytest

from providers.key4u_provider import Key4UConfig, Key4UProvider, config_from_env


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeAsyncClient:
    response = FakeResponse({})
    calls = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def provider(monkeypatch, *, public=True, admin=True):
    import providers.key4u_provider as module

    FakeAsyncClient.calls = []
    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)
    return Key4UProvider(
        Key4UConfig(
            enabled=True,
            public_enabled=public,
            admin_smoke_enabled=admin,
            api_key="sk-test",
            base_url="https://api.key4u.shop",
            openai_base_url="https://api.key4u.shop/v1",
            public_chat_base_url="https://api.key4u.vn",
        )
    )


def test_public_gate_is_separate_from_admin_smoke(monkeypatch):
    p = provider(monkeypatch, public=True, admin=False)
    assert p.chat_is_configured() is True
    assert p.is_configured() is False
    FakeAsyncClient.response = FakeResponse(
        {"id": "chatcmpl-safe", "choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}}
    )
    result = asyncio.run(p.chat_completion(messages=[{"role": "user", "content": "hello"}], model="claude-opus-4-8", require_usage=True))
    assert result["ok"] is True
    assert result["model"] == "claude-opus-4-8"
    assert result["text"] == "answer"
    assert result["provider_request_id"] == "chatcmpl-safe"
    assert FakeAsyncClient.calls[0][0] == "https://api.key4u.vn/v1/chat/completions"


def test_admin_smoke_cannot_enable_public_chat_or_native_document(monkeypatch):
    p = provider(monkeypatch, public=False, admin=True)

    assert p.chat_is_configured() is False
    chat = asyncio.run(
        p.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-opus-4-8",
        )
    )
    document = asyncio.run(
        p.document_completion(
            messages=[{"role": "user", "content": "read this"}],
            pdf_bytes=b"%PDF-1.7\nminimal",
        )
    )

    assert chat["ok"] is False
    assert document["ok"] is False
    assert FakeAsyncClient.calls == []


def test_public_opus_routes_ignore_environment_and_absolute_url_overrides(monkeypatch):
    import providers.key4u_provider as module

    monkeypatch.setattr(module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("KEY4U_ENABLED", "true")
    monkeypatch.setenv("KEY4U_PUBLIC_ENABLED", "true")
    monkeypatch.setenv("KEY4U_ADMIN_SMOKE_ENABLED", "false")
    monkeypatch.setenv("KEY4U_TOKEN", "sk-test")
    monkeypatch.setenv("KEY4U_PUBLIC_CHAT_BASE_URL", "https://attacker.invalid")
    monkeypatch.setenv("KEY4U_CHAT_BASE_URL", "https://attacker.invalid")
    monkeypatch.setenv("KEY4U_CHAT_COMPLETIONS_ENDPOINT", "https://attacker.invalid/stolen-chat")
    monkeypatch.setenv("KEY4U_CHAT_ENDPOINT", "https://attacker.invalid/stolen-chat")
    monkeypatch.setenv("KEY4U_MESSAGES_ENDPOINT", "https://attacker.invalid/stolen-pdf")
    FakeAsyncClient.calls = []
    p = Key4UProvider(config_from_env())

    FakeAsyncClient.response = FakeResponse(
        {
            "id": "chat-safe",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }
    )
    chat = asyncio.run(
        p.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-opus-4-8",
            require_usage=True,
        )
    )
    FakeAsyncClient.response = FakeResponse(
        {
            "id": "pdf-safe",
            "content": [{"type": "text", "text": "answer"}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
    )
    document = asyncio.run(
        p.document_completion(
            messages=[{"role": "user", "content": "read this"}],
            pdf_bytes=b"%PDF-1.7\nminimal",
        )
    )

    assert chat["ok"] is True
    assert document["ok"] is True
    assert [url for url, _ in FakeAsyncClient.calls] == [
        "https://api.key4u.vn/v1/chat/completions",
        "https://api.key4u.vn/v1/messages",
    ]


def test_text_image_payload_is_bounded_and_model_pinned(monkeypatch):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse(
        {"id": "req-safe", "choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "prompt_tokens_details": {"cached_tokens": 200}}}
    )
    image = "data:image/png;base64," + base64.b64encode(b"pngbytes").decode()
    messages = [{"role": "system", "content": "be concise"}, {"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": image}}]}]
    result = asyncio.run(p.chat_completion(messages=messages, model="some-other-model", require_usage=True))
    assert result["ok"] is True
    assert result["model"] == "claude-opus-4-8"
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 500
    assert result["cache_read_tokens"] == 200
    payload = FakeAsyncClient.calls[0][1]["json"]
    assert payload["model"] == "claude-opus-4-8"
    assert payload["messages"] == messages
    assert "responses" not in FakeAsyncClient.calls[0][0]


def test_modern_public_chat_preserves_openai_cache_semantics(monkeypatch):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse(
        {
            "id": "req-modern-cache",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {
                "prompt_tokens": 1_000,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": 200},
            },
        }
    )

    result = asyncio.run(
        p.public_chat_completion(messages=[{"role": "user", "content": "hello"}])
    )

    assert result["ok"] is True
    assert result["input_tokens"] == 1_000
    assert result["cache_read_tokens"] == 200
    assert result["input_tokens_include_cache"] is True
    assert result["usage"] == {
        "input_tokens": 1_000,
        "output_tokens": 50,
        "cache_read_tokens": 200,
        "input_tokens_include_cache": True,
    }


@pytest.mark.parametrize("cache_tokens", [True, 1.5, "not-a-number"])
def test_public_openai_rejects_malformed_cached_token_counts(monkeypatch, cache_tokens):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse(
        {
            "id": "req-invalid-cache",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {
                "prompt_tokens": 1_000,
                "completion_tokens": 50,
                "prompt_tokens_details": {"cached_tokens": cache_tokens},
            },
        }
    )

    result = asyncio.run(
        p.public_chat_completion(messages=[{"role": "user", "content": "hello"}])
    )

    assert result["ok"] is False
    assert result["error_class"] == "FAIL_USAGE_REQUIRED"


@pytest.mark.parametrize("cache_tokens", [True, 1.5, "not-a-number"])
def test_public_anthropic_rejects_malformed_cache_read_token_counts(monkeypatch, cache_tokens):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse(
        {
            "id": "msg-invalid-cache",
            "content": [{"type": "text", "text": "answer"}],
            "usage": {
                "input_tokens": 1_000,
                "output_tokens": 50,
                "cache_read_input_tokens": cache_tokens,
            },
        }
    )

    result = asyncio.run(
        p.public_anthropic_messages(messages=[{"role": "user", "content": "hello"}])
    )

    assert result["ok"] is False
    assert result["error_class"] == "FAIL_USAGE_REQUIRED"


def test_prompt_compatibility_uses_same_chat_route(monkeypatch):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse({"id": "req-safe", "choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    result = asyncio.run(p.chat_completion(prompt="hello", model="claude-opus-4-8", require_usage=True))
    assert result["ok"] is True
    assert FakeAsyncClient.calls[0][1]["json"]["messages"] == [{"role": "user", "content": "hello"}]


def test_pdf_uses_native_messages_endpoint_and_base64(monkeypatch):
    p = provider(monkeypatch)
    pdf = b"%PDF-1.7\nminimal"
    FakeAsyncClient.response = FakeResponse({"id": "msg-safe", "content": [{"type": "text", "text": "pdf answer"}], "usage": {"input_tokens": 1000, "output_tokens": 20, "cache_read_input_tokens": 200}})
    result = asyncio.run(
        p.document_completion(
            messages=[
                {"role": "system", "content": "Answer only from the document."},
                {"role": "user", "content": "read this"},
            ],
            pdf_bytes=pdf,
            model="claude-opus-4-8",
        )
    )
    assert result["ok"] is True
    assert result["text"] == "pdf answer"
    assert result["input_tokens"] == 1000
    assert result["output_tokens"] == 20
    assert result["cache_read_tokens"] == 200
    assert result["input_tokens_include_cache"] is False
    url, kwargs = FakeAsyncClient.calls[0]
    assert url == "https://api.key4u.vn/v1/messages"
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert "x-api-key" not in kwargs["headers"]
    assert kwargs["json"]["system"] == "Answer only from the document."
    assert all(message["role"] != "system" for message in kwargs["json"]["messages"])
    content = kwargs["json"]["messages"][-1]["content"]
    assert content[0]["type"] == "document"
    assert content[1] == {"type": "text", "text": "read this"}
    document = content[0]
    assert document["source"]["type"] == "base64"
    assert document["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(document["source"]["data"]) == pdf
    assert document["cache_control"] == {"type": "ephemeral"}


def test_missing_usage_or_request_id_fails_closed(monkeypatch):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse({"choices": [{"message": {"content": "answer"}}]})
    missing_usage = asyncio.run(p.chat_completion(messages=[{"role": "user", "content": "hello"}], model="claude-opus-4-8", require_usage=True))
    assert missing_usage["ok"] is False
    assert missing_usage["error_class"] == "FAIL_USAGE_MISSING"
    FakeAsyncClient.response = FakeResponse({"choices": [{"message": {"content": "answer"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}})
    missing_id = asyncio.run(p.chat_completion(messages=[{"role": "user", "content": "hello"}], model="claude-opus-4-8", require_usage=True))
    assert missing_id["ok"] is False
    assert missing_id["error_class"] == "FAIL_REQUEST_ID_MISSING"


def test_invalid_input_and_unknown_shape_do_not_call_fallback(monkeypatch):
    p = provider(monkeypatch)
    invalid = asyncio.run(p.chat_completion(messages=[{"role": "tool", "content": "no"}], model="claude-opus-4-8"))
    assert invalid["ok"] is False
    assert invalid["error_class"] == "FAIL_BAD_REQUEST"
    assert FakeAsyncClient.calls == []
    FakeAsyncClient.response = FakeResponse({"id": "safe", "unexpected": []})
    unknown = asyncio.run(p.chat_completion(messages=[{"role": "user", "content": "hello"}], model="claude-opus-4-8"))
    assert unknown["ok"] is False
    assert unknown["error_class"] == "FAIL_CONTENT_EMPTY"


def test_timeout_is_normalized(monkeypatch):
    import providers.key4u_provider as module

    class TimeoutClient(FakeAsyncClient):
        async def post(self, url, **kwargs):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(module.httpx, "AsyncClient", TimeoutClient)
    p = Key4UProvider(
        Key4UConfig(
            enabled=True,
            public_enabled=True,
            admin_smoke_enabled=False,
            api_key="sk-test",
            public_chat_base_url="https://api.key4u.vn",
        )
    )
    result = asyncio.run(p.chat_completion(messages=[{"role": "user", "content": "hello"}], model="claude-opus-4-8"))
    assert result["ok"] is False
    assert result["status"] == "FAIL_TIMEOUT"


def test_fractional_usage_is_rejected_instead_of_truncated(monkeypatch):
    p = provider(monkeypatch)
    FakeAsyncClient.response = FakeResponse(
        {
            "id": "req-safe",
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 1.5, "completion_tokens": 2},
        }
    )
    result = asyncio.run(
        p.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-opus-4-8",
            require_usage=True,
        )
    )
    assert result["ok"] is False
    assert result["error_class"] == "FAIL_USAGE_MISSING"


def test_admin_smoke_legacy_chat_keeps_existing_base_and_model(monkeypatch):
    p = provider(monkeypatch, public=False, admin=True)
    FakeAsyncClient.response = FakeResponse(
        {"id": "legacy-safe", "choices": [{"message": {"content": "legacy answer"}}]}
    )
    result = asyncio.run(p.chat_completion(prompt="hello", model="qwen-plus"))
    assert result["ok"] is True
    assert result["model"] == "qwen-plus"
    assert FakeAsyncClient.calls[0][0] == "https://api.key4u.shop/v1/chat/completions"
